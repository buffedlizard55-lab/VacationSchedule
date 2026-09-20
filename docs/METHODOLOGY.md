# Methodology

How "free time" is computed, and every judgement call behind it.

## The question being answered

For a given calendar day in Pacific Time, which minutes have **no** live sports
broadcast reachable on a standard AM/FM radio in the Outer Sunset (San Francisco
94122)?

## Sources of games

| League | Source | Status |
|---|---|---|
| MLB | `statsapi.mlb.com/api/v1/schedule` (official) | Verified for 2026 and 2027; **fetched live by the app** |
| NFL radio | `westwoodonesports.com/nfl-schedule/` (national radio) + `49ers.com/schedule/` | Verified for 2026 radio records |
| NFL full slate | NFL official schedule release PDF / `nfl.com/nfl-schedule-release/` | 272 official 2026 regular-season matchups; flexible dates and Week 18 TBD where published |
| NCAAF (Stanford, Cal) | `gostanford.com`, `calbears.com` | Verified, partial kickoffs |
| NCAAF (Westwood One national radio) | `westwoodonesports.com/ncaa-football` | Verified (station list); many air times TBD |
| MLS (Earthquakes) | `sjearthquakes.com` | Verified, partial kickoffs |
| Season frames 2026–2029 | `statsapi.mlb.com/api/v1/seasons`, NFL announcements | 2026 verified; 2027 MLB verified; 2028–29 **estimated** (MLB + NFL) |

**Athletics (A's) games** are included through the live MLB feed (all 30 clubs are
retrieved). Their Bay Area radio home is **KSTE 650 AM (Sacramento) + KNEW 960 AM**
— they are *not* on KNBR (see SOURCES.md and IR-11).

Full list with retrieval dates: [`SOURCES.md`](SOURCES.md).

## The engine

`scripts/lib_windows.py` (Python) and `site/app.js` (browser) implement the same
algorithm. `tests/test_parity_js.py` runs the real `site/app.js` under Node and
diffs it against the Python engine for **every date in the generated bundle plus the DST
boundaries**; they agree to the minute.

### Step 1 — build an interval per game

Every game becomes a half-open UTC interval `[start, end)`.

### Step 2 — clip to the day

`clip(interval, day_start, day_end)` trims an interval to the day being reported.
**Clipping is not the same as filtering.** An overnight game (e.g. a West Coast
game ending after midnight PT) overlaps two dates; filtering selects it for both
but leaves it full length, double-counting it. Clipping splits it correctly.

### Step 3 — merge overlapping intervals

Adjacent or overlapping games collapse into one busy block. Merging promotes the
block to `high` priority if any constituent is high priority, and marks it
`time_confirmed = False` if any constituent is unconfirmed.

### Step 4 — complement

Free windows are the gaps between merged busy blocks, bounded by the day's start
and end. This is what produces the user's own example: games 1–5 PM and 8–10 PM
leave **5–8 PM free** rather than marking the whole day busy.

### Step 5 — report

Per day: `busy_minutes`, `free_minutes`, `is_free_day`, the free windows, the busy
windows, `has_high_priority`, `has_unconfirmed_times`, `unconfirmed_minutes`, and
`tbd_unresolved`.

## Timezone handling

All arithmetic happens in UTC. Two rules matter:

**Rule 1 — normalize before subtracting.** CPython documents that when two aware
datetimes share the *same* `tzinfo` object, subtraction and ordering ignore the UTC
offset and use naive wall-clock semantics. So `(aware_end - aware_start)` where both
carry `ZoneInfo("America/Los_Angeles")` returns **24 hours for a 25-hour DST day**.
Verified in-sandbox:

```
n - d                                -> timedelta(days=1)                  # 24h  WRONG
n.astimezone(UTC) - d.astimezone(UTC) -> timedelta(days=1, seconds=3600)    # 25h  RIGHT
```

`Interval.__init__` therefore converts to UTC on construction, and `span_minutes()`
re-normalizes defensively. This was a real bug: every DST day was silently read as
24 hours.

**Rule 2 — iterate when converting wall clock to UTC.** Pacific Time's offset
changes twice a year, so `wall_clock - offset(wall_clock)` can land on the wrong
side of a transition. Both engines iterate three times to converge.

Verified day lengths: **2026-11-01 = 1500 min (25 h)**, **2026-03-08 = 1380 min
(23 h)**, ordinary days = 1440. Both engines agree on all of these.

## Durations

Game length is not published in advance, so research averages are used. They are
the *only* invented numbers in the busy-block computation.

| League | Minutes | Basis |
|---|---|---|
| MLB | **164** | 2:44, the actual 2026 average |
| NFL | **192** | 3:12 including the 12-minute halftime |
| NCAA FBS | **204** | 3:24 including the 20-minute halftime |
| MLS | **120** | ~2:00 |

These are averages, not guarantees. A rain-delayed MLB game can run well past its
window, and the engine has no way to know. The effect is that reported free time is
**optimistic at the tail end of a game**.

## Radio air time widening

Westwood One publishes **radio air time in Eastern Time, not kickoff time.** The
pre-game show starts before the ball is kicked. The engine blocks from the earlier
of the two, so a Westwood One game blocks slightly more than its nominal duration.

## The TBD envelope

Some games have an **official date but no announced start time.** These are never
skipped. Skipping is what caused the bug this project was built to fix: an earlier
version dropped un-timed MLB postseason games and reported 2026-09-29 (Wild Card
day) as a **free day**.

Instead, an un-timed game blocks a conservative envelope in Pacific Time:

| League | Envelope (PT) | Rationale |
|---|---|---|
| MLB | 15:00 – 23:59 | Latest plausible first pitch through end of game |
| NFL | 09:00 – 23:59 | Includes 9:30 AM PT London/Europe games |
| NCAAF | 11:00 – 23:59 | Noon ET through late West Coast kickoffs |
| MLS | 16:00 – 23:59 | Evening kickoffs |

Envelopes are rendered at reduced opacity and flagged `Time TBD` in the UI so a
conservative block is never mistaken for a confirmed schedule. `unconfirmed_minutes`
reports how much of the day's busy time is envelope rather than confirmed.

## The MLB placeholder sentinel

The MLB Stats API does not omit un-timed postseason games. It serves them with
**placeholder teams and a fabricated `gameDate` of `...T07:33:00Z`** — 12:33 AM PT,
which no real game would occupy. `MLB_TBD_SENTINEL_UTC` and `is_tbd_utc()` detect
this. The sentinel instant is never surfaced as a real time; the game is routed to
the MLB envelope instead.

## High-priority teams

Per the user's instruction, these are flagged `high`:

**San Francisco Giants, Athletics, San Francisco 49ers** (explicit), plus **Stanford,
California, San Jose Earthquakes** (in the Bay Area coverage set).

## What is *not* covered

The engine only knows about the sources above. Warriors (NBA), Sharks (NHL), Stanford
and Cal basketball, USF, and high school sports are **out of scope** and a day marked
"free" may still carry their broadcasts. See [`LIMITATIONS-NEXT.md`](LIMITATIONS-NEXT.md).

---

# Revision 2026-09-20 (second pass) — sections, the season frame, and the schedule-frame records

## Coverage sections

The request defines three sets of games and asks to compare them. A **section** is a
definition of "busy"; every report on the site is generated once per section.

| Section | Busy when any of these is on air |
|---|---|
| 1 | MLB (all 30 clubs) · 49ers (preseason/regular/postseason) · Westwood One national NFL radio |
| 2 | Section 1 + Stanford NCAAF + California NCAAF |
| 3 | Section 2 + San Jose Earthquakes MLS |
| all | Everything the project tracks (adds Westwood One national **NCAA** football) |

Implementation: each game record carries a `tags` list at build time
(`MLB`, `NFL:49ers`, `NFL:national`, `NCAAF:Stanford`, `NCAAF:California`,
`NCAAF:national`, `MLS:Earthquakes`). `scripts/build_data.py` converts tags to a
`sections` list using the `required_tags` in `data/verified/profiles.json`, and both
engines filter with the same one-line membership test:

```python
def game_in_scope(game, scope):
    return scope is None or scope == "all" or scope in (game.get("sections") or [])
```

`None` and `"all"` mean "no filtering", which keeps every pre-existing caller and test
working unchanged.

**Westwood One national NCAA football is deliberately in no section.** The request lists
Westwood One for the NFL only, so those games are tracked, shown on the day board as
"not counted in Section N", and included only under the `all` scope.

## The MLB season frame (a second safety net)

The 2026 postseason is carried per date. The rest of the MLB season is not: bundling
2,430 games into the snapshot would be a large, stale duplicate of a live feed. That
created a hole — a date inside the MLB season with no bundled game read as **free**.

`lib_windows.mlb_frame_for()` closes it. Each year carries a frame
(`data/verified/seasons.json` → bundle `mlb_frames`): Spring Training start through
postseason end, with an `estimated` flag. If a date falls inside a frame, the selected
scope includes MLB, and the bundle has no MLB game on that date, the engine blocks
`TBD_ENVELOPE_PT["MLB"]` (15:00–23:59 PT) with `time_confirmed = False` and reports
`mlb_frame_fallback = true` so the UI can say why.

**Exception — `complete_ranges`.** For 2026 the bundle *does* hold the complete per-date
list from 2026-09-28 to 2026-10-31 (the postseason, read game-by-game from the Stats
API). Inside those ranges a date with no game is genuinely free, so the frame fallback
is suppressed. That is what makes 2026-10-02, 10-21 and 10-22 real free days rather than
false negatives.

The live feed supersedes the frame: when the page successfully fetches a date from
`statsapi.mlb.com`, the frame block is not applied for that date.

## NFL round records (day-board completeness)

The day board works from games, not spans. The 49ers feed lists only the 49ers, and the
Westwood One feed is published as far as the Week 18 slate — so before this revision,
**2027-01-17 (Wild Card Sunday) read as a free day** whenever the 49ers were not the
listed participant, even though Westwood One carries every playoff round nationally.

`scripts/nfl_calendar.py` now owns the NFL calendar and `build_data.from_nfl_calendar()`
emits one date-level record per playoff round (participants TBA, kickoff TBA, envelope
blocked) plus the Pro Bowl Games. Rounds for the 2026-27 season are VERIFIED against the
NFL's key-dates release; later seasons are derived from the same verified template and
labelled ESTIMATED in the record's `status` field.

## The full NFL slate is reference data, not a radio claim

`data/verified/nfl_regular_2026.csv` contains all 272 official 2026 regular-season
matchups from the NFL by-week release. Known dates and Eastern kickoffs are preserved
and converted to Pacific Time only in the browser reference panel. Flexible Week 16/17
assignments and every Week 18 date/kickoff remain `TBD`; no third-party future-date
field is imported to fill them.

The bundle exposes this as `nfl_schedule_2026`. It is intentionally separate from
`games`: the Section 1–3 interval engine counts the Westwood One national broadcast
records and the date-level radio backstop, not every game in the league as if it were
broadcast locally. A day board therefore gives both answers: the radio interval that
changes free time and the actual NFL games scheduled that day.

`nfl_calendar.season_game_dates(2026)` uses the exact regular-season date set, rather
than assuming every December Saturday contains a game. The separate 49ers source owns
preseason occupancy; old generic 2026 season-frame rows are not emitted.

## The week-window proof

The vacation analysis blocks September–December as one continuous NFL span, and the
Stanford/Cal and MLS seasons as continuous spans. That is conservative. It is also
provably unable to hide the thing being asked about:

> a run of 7 consecutive days always contains a Sunday, the NFL plays every Sunday,
> college football plays Saturdays and MLS plays weekends — so no 7-day window can exist
> inside those seasons.

`tests/test_free_time.py::TestWeekWindowInvariant::test_no_week_long_run_inside_the_nfl_season`
asserts it directly: for every section and both interpretations, every run of 7+ days
ends before that season's Hall of Fame Game. The spans therefore overstate *day*
counts (a Tuesday in November is marked busy even though no NFL game is on) but never
overstate the *answer*.

## Durations — re-checked 2026-09-20

| League | Used | Evidence |
|---|---|---|
| MLB | 164 min (2:44) | SBJ 2026-07-14: average nine-inning game through 2026-07-08 ≈ **2:42**, up for a second straight year but still 15 % shorter than pre-pitch-clock. 164 is the researched average rounded up for safety. |
| NFL | 192 min (3:12) | Widely reported NFL average 3:12 including a 12-minute halftime. |
| NCAAF | 204 min (3:24) | FBS average 3:24–3:26 with a 20-minute halftime. |
| MLS | 120 min (2:00) | 90 minutes plus stoppage plus a 15-minute halftime. |

A game whose start time is unannounced is *not* given an assumed duration: it is blocked
with the league's TBD envelope instead, which already exceeds any plausible game length.
