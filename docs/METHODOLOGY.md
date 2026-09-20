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
| NFL | `westwoodonesports.com/nfl-schedule/` (national radio) + `49ers.com/schedule/` | Verified for 2026 |
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
diffs it against the Python engine for **all 95 dates in the bundle plus the DST
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
