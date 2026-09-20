# Irregularities flagged for review

Every place where a source was wrong, inconsistent, ambiguous, or silent. Nothing
here was silently resolved — each item states what was found, what was done about
it, and what remains uncertain.

---

## IR-01 — 49ers coverage gaps (HIGH)

**Found:** the `49ers.com` retrieval captured most of the 2026 season but is missing
**Weeks 1, 2 and 8, and every preseason game.** Week 18 is listed as `TBD`.

**Impact:** those dates would read as **free** when 49ers games actually occur. This is
exactly the class of bug the user reported on a previous site.

**Done:** each gap is emitted into the `unresolved` array with its reason, and the UI
shows all 50 unresolved items on the **Needs Review** tab. **The gaps are labelled, not
papered over** — but the affected days are *not* conservatively blocked, because no
date is known to block.

**Still open:** fill from a live NFL feed (see `LIMITATIONS-NEXT.md`).

---

## IR-02 — MLB postseason times are fabricated, not merely absent (HIGH)

**Found:** `statsapi.mlb.com` serves 2026 postseason games with **placeholder team
names** and `gameDate = ...T07:33:00Z`, i.e. **12:33 AM Pacific**. No real first pitch
happens at that hour.

**Why it matters:** a naive parser reads `07:33:00Z` as a legitimate kickoff and
reports the whole afternoon and evening as free.

**Done:** `MLB_TBD_SENTINEL_UTC` + `is_tbd_utc()` detect the sentinel. Affected games
are routed to the conservative MLB envelope (**15:00–23:59 PT**) and flagged
`time_confirmed = False`. The sentinel instant never surfaces as a time. Test:
`test_tbd_mlb_game_blocks_conservatively`.

**Still open:** the real times. They do not exist anywhere yet.

---

## IR-03 — `postSeasonStartDate` disagrees with the first actual game (LOW)

**Found:** the Stats API reports MLB `postSeasonStartDate = 2026-09-28`, but the first
scheduled postseason games are **2026-09-29** (Wild Card Game 1). 2026-09-28 is a
travel/off day.

**Done:** both dates are blocked. The season frame keeps the API's 09-28 with a note;
the game list carries the 09-29 fixtures. No vacation window is affected.

---

## IR-04 — Cal @ Syracuse kickoff: one source disagreed (MEDIUM)

**Found:** `calfootball.com`'s JSON-LD gave **09:30 PT** for Cal @ Syracuse. Every other
source, including `calbears.com`, gave **12:30 PT**.

**Assessment:** 09:30 PT is a 12:30 PM ET kickoff. No ACC game kicks off at 12:30 ET
on a Saturday. Almost certainly a **PT/ET labelling error** in the JSON-LD.

**Done:** corrected to **12:30 PT** in `data/verified/bay_area_2026.json`, following
the primary source. Logged here because it is a genuine source conflict.

**General rule adopted:** where a secondary source conflicts with a league-owned
source, the league-owned source wins.

---

## IR-05 — 11 of 24 Stanford/Cal games have no announced kickoff (MEDIUM)

**Found:** Stanford announced times for only "select" games. Across both programmes,
**11 of 24** fixtures have a verified date but no time.

**Done:** those dates are envelope-blocked **11:00–23:59 PT** rather than guessed.
They render at reduced opacity with a `Time TBD` chip.

**Trade-off stated plainly:** this makes some genuinely free afternoons look busy.
That is deliberate — the user's stated priority is never recommending a vacation on a
day that has a game.

---

## IR-06 — Earthquakes Matchday 33 kickoff is "Time TBD" (LOW)

**Found:** the club's own release lists the **2026-10-31** match vs Real Salt Lake
with `Time TBD`.

**Done:** MLS envelope **16:00–23:59 PT** applied. Note that on this date the NCAAF
envelope (11:00–23:59) already subsumes it, so the merged block is 11:00–23:59 =
**779 minutes**, entirely unconfirmed.

---

## IR-07 — Earthquakes February–July fixtures were never retrieved (MEDIUM)

**Found:** only matches from **2026-08-01** onward are in the snapshot. The club
release confirms the season opened **2026-02-21**, so roughly five months of MLS
fixtures are absent.

**Impact:** MLS-heavy spring dates may read as free.

**Mitigating:** those dates are already blocked by MLB Spring Training, so no
vacation window in this analysis is affected. Still a real coverage hole.

---

## IR-08 — Westwood One publishes air time, not kickoff (MEDIUM)

**Found:** the schedule page lists **Eastern Time radio air times**, which precede
kickoff because of the pre-game show.

**Done:** the engine blocks from `min(air_time, kickoff)`. Westwood One games
therefore block slightly longer than their nominal duration.

**Also noted:** Denver's stadium is written two different ways on the same page —
"Empower Field at Mile High" and "Mile High Stadium". Cosmetic; no action.

---

## IR-09 — 8 Westwood One slots have no teams announced (LOW)

**Found:** slots such as the **2026-12-26** Saturday doubleheader list no teams.

**Done:** the date is still blocked (Westwood One is broadcasting), and the entry is
flagged unresolved. Blocking on an unknown opponent is the correct behaviour here.

---

## IR-10 — Westwood One's San Francisco affiliate is unconfirmed (MEDIUM)

**Found:** the Station Finder does not clearly confirm which Bay Area station carries
the national feed. **KNBR is presumed but not verified.**

**Impact:** if the affiliate were a weaker or differently-located station, Outer Sunset
reception could differ.

**Not resolved.** Flagged for manual review.

---

## IR-11 — The Athletics' Bay Area radio flagship is unidentified (LOW)

**Found:** no source consulted confirmed the A's flagship station for 2026.

**Impact:** A's games are flagged high priority per the user's instruction, but a
listener may not be able to receive them on KNBR.

**Not resolved.**

---

## IR-12 — Super Bowl LXIII has no confirmed date (MEDIUM)

**Found:** the NFL has awarded **Super Bowl LXIII to Allegiant Stadium, Las Vegas**
for the 2028 season, but has **not announced the date.**

**Done:** estimated as the **second Sunday of February 2029 = 2029-02-11**, and marked
`ESTIMATED`.

**Sensitivity:** this single date sets the best 2029 vacation window. If the Super Bowl
moves to the first Sunday (Feb 4), the window grows to **14 days**. If it moves to
Feb 18, the window **disappears**. 2029 is the least reliable year in the analysis
for this reason.

**Correction of record:** an earlier assumption placed Super Bowl LXIII at Levi's
Stadium. It is **Allegiant Stadium, Las Vegas.**

---

## IR-13 — 2027–2029 MLB and NFL seasons are unreleased (HIGH, by design)

**Found:** `statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029`
returns **2026 only.** No 2027, 2028 or 2029 records exist.

**Done:** those years are computed from the 2026 verified frame plus each league's
published scheduling rules, and every row carries `status: ESTIMATED` with a `basis`
field explaining the reasoning and a `source` field reading **"NOT RELEASED"** rather
than a fabricated URL.

This is the user's explicit requirement: estimates must be clearly marked as
estimates, not presented as real schedules.

---

## IR-14 — A same-`tzinfo` subtraction bug made every DST day 24 hours (HIGH, fixed)

**Found:** Python's `datetime` arithmetic ignores `utcoffset()` when two aware
datetimes share the *same* `tzinfo` object. So
`aware_end - aware_start` returned **24 hours for a 25-hour day.**

Proof run in-sandbox:

```
n - d                                 -> timedelta(days=1)                # 24h  WRONG
n.astimezone(UTC) - d.astimezone(UTC) -> timedelta(days=1, seconds=3600)   # 25h  RIGHT
```

A control using fixed-offset `timezone(timedelta(hours=-7))` vs `-8` correctly gave
25 h, confirming the cause was the shared `ZoneInfo`, not tzdata.

**Impact:** 2026-11-01 (a Sunday with a full NFL slate) was computed as 1440 minutes
instead of **1500**. Reported free time on DST transition days was wrong.

**Fixed:** `Interval.__init__` normalizes to UTC on construction; `span_minutes()`
re-normalizes defensively; `local_day_bounds()` and `local_wall_clock()` convert
before arithmetic. Regression tests: `test_span_minutes_is_dst_safe`,
`test_day_report_uses_true_dst_day_length`, `test_dst_days_match`.

**Rule adopted:** always `.astimezone(timezone.utc)` before subtracting or comparing
aware datetimes.

---

## IR-15 — Filtering is not clipping (HIGH, fixed)

**Found:** `intervals_for_day` selected intervals overlapping a day but left them at
full length. An overnight game was counted at **full duration on both dates.**

**Proof:** a test with an overnight fixture reported `busy_minutes = 164.0` where only
**44.0** minutes belong to the reported date.

**Fixed:** added `clip(iv, day_start, day_end)`, used by both `intervals_for_day` and
`free_windows`. Test: `test_overnight_game_blocks_two_dates`.

---

## IR-16 — Un-timed games were skipped entirely (HIGH, fixed)

**Found:** `game_to_interval` returned `None` for a game with a verified date but no
time. The day then looked empty and was reported **free**.

**Concrete failure:** **2026-09-29** (MLB Wild Card Game 1) was reported as a free
day — precisely the bug the user reported.

**Fixed:** un-timed games now block their league's TBD envelope and are flagged
`time_confirmed = False`. `day_report` gained `has_unconfirmed_times`,
`unconfirmed_minutes`, and `is_free_day = not merged`. Tests:
`test_tbd_mlb_game_blocks_conservatively`, `test_postseason_dates_are_never_free`,
`test_no_game_day_is_reported_free` (asserts **no** date carrying a game reads free,
across all 342 bundle rows).

---

## IR-17 — The whole MLB regular season was missing from the offline bundle (HIGH, fixed)

**Found:** the bundle held **30 MLB rows, all postseason.** `mlb_regular_season_days()`
computed all **187 regular-season dates** but only used them for a metadata count — they
never became blocking intervals.

**Concrete failure:** every regular-season date read as a **completely free day** whenever
the app ran offline, including **Opening Day 2026-03-25**:

```
2026-03-25: is_free_day=True  busy=0 min  free=1440   <- WRONG
2026-06-14: is_free_day=True  busy=0 min  free=1440   <- WRONG
2026-07-04: is_free_day=True  busy=0 min  free=1440   <- WRONG
```

The live `statsapi.mlb.com` fetch masked this online, which is why it survived review.
It is the same bug class as IR-16 and IR-01, one level up: a whole season rather than one
game.

**Fixed:** `from_mlb_regular_season()` now emits one marker per regular-season date
(**217 MLB rows, 342 total**). Each carries `time_status: "season_in_progress"`, an empty
`start_utc` (no time is invented) and `envelope_pt: ["10:00", "23:59"]` — the regular
season needs a wider envelope than the postseason because day games start ~10:05 PT.
The app still supersedes markers with live per-game times.

Also fixed in the engine: `game_to_interval` checked `if not start_raw: return None`
*before* the unconfirmed-time branch, so a busy-on-a-known-date row with no time vanished.
The check order is now reversed.

Tests: `test_mlb_regular_season_dates_are_never_free_offline`,
`test_mlb_regular_envelope_covers_day_games`, `test_every_game_is_placeable`.

---

## IR-18 — Dates with no data were reported as free (HIGH, fixed)

**Found:** `day_report` treated an empty interval list as "free" regardless of whether the
dataset covered that date at all. The bundle ends **2027-01-10**, so every later date read
as a green **FULLY FREE**:

```
2027-06-15: is_free_day=True   <- no data at all
2029-02-14: is_free_day=True   <- no data at all
```

**Why it matters:** this is the exact failure the user reported — a site confidently
showing free time where it has no idea. "We have not looked" and "nothing is on" are
different claims and must not render identically.

**Fixed:** `coverage_span()` derives the span the dataset speaks for, and `day_report`
returns `data_coverage` ∈ `before | within | after | none`. A day is free only when
`data_coverage == "within"` **and** nothing is scheduled. The UI gained a third, amber
**NO DATA** verdict, visually distinct from green FREE and red BUSY.

Navigation is deliberately **not** clamped to the span: walking past the edge shows the
amber verdict, which teaches the boundary instead of silently pinning the date and making
the buttons look broken. `min`/`max` on the date input still steer the native picker.

Tests: `test_dates_outside_coverage_are_never_reported_free`, plus render checks asserting
an out-of-coverage date shows `NO DATA` and never `FULLY FREE`.
