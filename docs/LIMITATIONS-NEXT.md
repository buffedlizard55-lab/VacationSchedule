# Limitations and suggested next work

Written for the next session, refreshed after the 2026-09-20 review pass. Everything
here is a real gap, not a hypothetical.

---

## Part 1 — The honest headline limitation

### There is no window in any year with zero live Bay Area sports radio

The site answers the question **as scoped**: no MLB, no 49ers, no Earthquakes, no
Stanford/Cal NCAAF, no Westwood One national football. Under that definition, real
windows exist (see VACATION-WINDOWS.md).

But a listener in the Outer Sunset with a standard AM/FM radio on a "free" day will
still hear live sports. **Not covered by this project:**

| Sport | Team(s) | Season | On KNBR? |
|---|---|---|---|
| NBA | Golden State Warriors | Oct – Jun | No (other outlets) |
| NHL | San Jose Sharks | Oct – Jun | No (other outlets) |
| NCAA basketball | Stanford, Cal | Nov – Mar | **Yes** |
| NCAA basketball | USF men's | Nov – Mar | **Yes** |
| High school / other | various | varies | sometimes |

**This matters most for the February windows.** Mid-February is the peak of college
basketball season, and KNBR carries Stanford, Cal and USF. A "free" day in February
will almost certainly have live college basketball on KNBR.

**Nothing in this repo should be read as "no sports radio."** It means "none of the
sports you listed."

### Scope decision: Warriors and Sharks remain outside Sections 1–3

For this release, **do not add Golden State Warriors (KGMZ 95.7) or San Jose Sharks
games to the scored sections**. The requested definitions are intentionally preserved:
Section 1 is MLB/49ers/Westwood One NFL, Section 2 adds Stanford and Cal football, and
Section 3 adds the Earthquakes. Adding NBA/NHL games would silently redefine Section 3
and make its 12-day result incomparable to the requested answer. Their broadcasts are
therefore an explicit limitation, not a claim that a displayed free window is quiet on
all Bay Area radio. A future opt-in fourth scope may add them after official schedules,
radio carriage, and the 94122 reception assumptions are sourced together.

---

## Part 2 — Data gaps, ranked by impact (updated 2026-09-20)

### 1. MLB 2026 postseason first pitch times do not exist (HIGH — resolves itself)

Round dates official (Wild Card Sep 29–Oct 1, Division Series Oct 3–10, LCS Oct 11–20,
World Series Oct 23–31); **matchups and times are still TBD** (API serves placeholder
teams + `07:33:00Z` sentinel). Clinched so far (as of 2026-09-19): Rays, Brewers,
Dodgers, Yankees, Braves. **Re-run the live fetch after 2026-09-27** — the bracket will
fill and the code already handles it via the live `statsapi.mlb.com` call.

### 2. NFL Week 18 and national-radio assignments (MEDIUM — resolves itself)

The complete official 272-game 2026 regular-season matchup slate is now bundled in
`data/verified/nfl_regular_2026.csv` and `site/data/schedule-data.json`. Week 16/17
flexible-game assignments and Week 18 date/kickoff fields remain explicitly TBD. The
Westwood One page identifies the national slot, but not always its matchup yet. The day
board shows the actual league matchups in a separate reference panel and uses a
conservative radio envelope when the selection is not published; it never treats every
NFL game as a Bay Area broadcast.

### 3. 11 of 24 Stanford/Cal games are envelope-blocked (MEDIUM)

Real dates, no announced kickoff (11:00–23:59 PT). Over-blocks by design. Re-check
`gostanford.com`/`calbears.com` closer to game day (times announced ~2 weeks out).

### 4. Earthquakes February–July fixtures missing (MEDIUM)

Only 2026-08-01 onward is in the snapshot. Mitigated because MLB Spring Training blocks
those dates, but MLS-only analysis is incomplete. **Note:** after 2026 the A's and
Earthquakes presence in the data stops — a gap for 2027+ (see Part 3).

### 5. Bowl games / CFP not modelled (MEDIUM)

Stanford/Cal bowl assignments undetermined. ~2026-12-19 → 2027-01-01; CFP NCG 2027-01-11
at Allegiant Stadium. Late-December dates may be under-blocked.

### 6. Westwood One NCAA air times partly TBD (LOW)

7 of 13 Westwood One NCAA games have no published air time; envelope-blocked. Air times
are typically announced ~a week ahead.

### 7. KZSU 90.1 (Stanford) / KGO 810 (Cal) (LOW)

Plausible additional outlets, not confirmed for 2026.

### 8. Durations are industry averages, not league statistics (LOW)

MLB 164 min, NFL 192, NCAA 204, MLS 120 (sourced from industry reporting, not leagues).
Tail-of-game free time is optimistic.

**Resolved this pass:** 49ers preseason/Week 1/2/6/8-BYE (IR-17), NFL opener date (IR-18),
Westwood One SF affiliate = KNBR (IR-10), A's flagship = KSTE 650/KNEW 960 (IR-11).

---

## Part 3 — Still unresolved (flagged for review)

### 2027 MLB provisional (CBA)

2027 MLB is VERIFIED but **provisional**: the CBA expires 2026-12-01; a lockout could
delay/cancel the season. Re-check after a new CBA is signed (IR-19).

### 2028–2029 MLB; 2027–2029 NFL

Unreleased. `statsapi.mlb.com/api/v1/seasons?season=2028` (and 2029) return an empty
list — MLB's own signal those schedules don't exist. All 2027+ NFL beyond the Super
Bowl sites is a day-of-week template (ESTIMATED).

### Super Bowl LXIII's exact date (2029)

Las Vegas/Allegiant confirmed; date estimated 2029-02-11 (2nd Sunday). Sensitivity:
if it moves to the 1st Sunday or later, the late-Jan/early-Feb window shifts.

### A's and Earthquakes after 2026

The A's plan a Las Vegas move (~2028); their 2027+ Bay Area radio (KNEW 960) and the
Earthquakes' 2027+ schedules/fixtures are not retrieved. Any 2027+ day analysis that
depends on those teams is incomplete until filled.

---

## Part 4 — Current priority order

Ordered by value per unit of effort, and kept explicit so a later refresh does not
silently change the answer.

1. **Re-fetch 2026 MLB postseason first-pitch data after 2026-09-27.** MLB currently
   returns the `07:33:00Z` sentinel; replace only those unresolved first pitches with
   official values and retain the visible TBD flags for anything still unpublished.
2. **Maintain the complete 272-game NFL schedule.** The first official snapshot is now
   bundled. Refresh flexible-date assignments and Week 18 as the NFL publishes them;
   keep the full slate as display/reference data and keep Westwood One radio occupancy
   separate.
3. **Keep the Warriors/Sharks scope decision visible.** They remain out of Sections 1–3
   for this release. If the scope is reopened, add them as an opt-in section only after
   official schedules and KGMZ/Sharks radio carriage are verified.
4. **Keep parity variants batched.** `tests/test_parity_js.py` now starts one Node
   harness and runs `all:0`, `all:1`, `1:1`, and `3:1` in the same process.

### Other follow-up work

5. Re-check Stanford/Cal kickoff announcements ~2 weeks before each game.
6. Fetch the full Earthquakes fixture list and the A's 2027 radio plan.
7. Add college basketball (Stanford, Cal, USF on KNBR) only as a separately named scope.
8. Model bowl games / CFP once assignments are known, and refresh Westwood One playoff
   matchup labels once published.
9. Add confidence scoring, a weekly/monthly calendar view, reception modelling, and
   automated freshness/diff checks.

---

## Part 5 — Invariants that must not regress

If you change the engine, keep these true. All are covered by tests.

| Invariant | Test |
|---|---|
| No date carrying a game reads free | `test_no_game_day_is_reported_free` |
| Every 2026 postseason date reads occupied | `test_postseason_dates_are_never_free` |
| An un-timed game blocks, never disappears | `test_tbd_mlb_game_blocks_conservatively` |
| The `07:33:00Z` sentinel never surfaces as a time | `test_tbd_mlb_game_blocks_conservatively` |
| Overnight games split across both dates | `test_overnight_game_blocks_two_dates` |
| DST days are 23 h / 25 h, not 24 h | `test_span_minutes_is_dst_safe`, `test_day_report_uses_true_dst_day_length` |
| Games 1–5 and 8–10 PM leave 5–8 PM free | `test_user_stated_example_1pm_to_5pm_and_8pm_to_10pm` |
| JS and Python agree to the minute on all bundle dates | `test_day_reports_match_exactly` |
| The NFL playoff date template reproduces 2026-27 | `test_previous_season_playoff_dates_are_verified_against_2026_27` |
| Estimated seasons are never labelled verified | `test_2027_is_verified_and_2028_2029_estimated` |

**Two rules worth repeating:**

- Always `.astimezone(timezone.utc)` before subtracting or comparing aware datetimes.
  CPython silently returns wall-clock time when both sides share a `tzinfo`. See IR-14.
- An un-timed game must **block**, not vanish. Returning `None` is how a Wild Card day
  got reported as free. See IR-16.

---

# Revision 2026-09-20 (after the sections/PR pass)

## Stale items corrected in this revision

- **IR-12 is closed.** Super Bowl LXIII is **2029-02-11 at Allegiant Stadium, Las
  Vegas**, announced by the NFL on 2026-03-30. It was previously carried as an
  estimate. `data/verified/seasons.json` said otherwise for the 2028 season; that entry
  was corrected and `scripts/nfl_calendar.py` is now the single source of truth for
  Super Bowl, Pro Bowl and playoff-round dates. `data/verified/*.json` should not
  restate them.
- **The three sections did not exist** when this document was first written. The advice
  below ("cover the whole NFL season", "add college basketball") still stands, but the
  cost of a gap is now section-specific and the Compare tab shows which section is
  binding.
- **The 2026 NFL slate is now bundled, with radio kept separate.** The official NFL
  PDF supplies all 272 regular-season matchups and the published dates/times. Flexible
  Week 16/17 assignments and Week 18 remain visibly TBD. The day board shows the full
  slate as reference data and only the Westwood One selection/backstop affects the
  Section 1–3 busy intervals.
- **Warriors/Sharks scope is decided for this release.** They remain outside the three
  requested sections and are called out as a limitation rather than silently included.

## What is genuinely still blocking a good product

### High

1. **2026 MLB postseason times (IR-24).** Every game is the `07:33:00Z` sentinel. The
   recommendations are durations, not clock times, until MLB sets first pitch. Re-fetch
   from 2026-09-27. This is the single largest source of `Time TBD` chips.
2. **The 2026 NFL full slate is complete, but radio selection is not always published.**
   `data/verified/nfl_regular_2026.csv` contains 272 official matchups and the day board
   displays them as a clearly separated reference. The Westwood One source remains the
   occupancy source; dates without a published selection use a conservative envelope and
   are flagged. Week 18 dates/times and flexible Week 16/17 assignments stay TBD.
3. **Basketball and hockey are intentionally out of scope.** Warriors (KGMZ 95.7) and
   Sharks games land inside the recommended windows, but this release preserves the
   requested Section 1/2/3 definitions. They are listed as a limitation, not silently
   mixed into Section 3. An opt-in scope requires a later sourced decision.
4. **2028-2029 are estimates in the strictest sense.** The NFL has not released those
   schedules, and MLB's 2028/2029 seasons return empty from the Stats API. The windows
   shown for those years are derived from the league calendars and are labelled
   ESTIMATED on every row. Do not quote them as schedules.

### Medium

5. **College basketball** (Stanford, Cal, USF on KNBR) runs November–March and would
   bite the February corridors the same way MLS bites the regular-season one.
6. **Bowl games and the CFP** are a single ESTIMATED span past 2027-01-01; the actual
   matchups are only known in December.
7. **MLS is bundled through 2026-11-07.** The 2027-2029 MLS schedules do not exist yet;
   the analysis carries a season span instead, and Section 3's answer for those years
   depends on that span being roughly right.
8. **The Westwood One affiliate table is labelled 2025** (IR-23). One constant to
   update, but it is the only evidence for the San Francisco affiliate list.
9. **The A's Bay Area signal is unverified** (IR-28). KNEW 960 is the Bay Area affiliate;
   whether KSTE 650 covers 94122 from Rancho Cordova is undocumented.
10. **Baseball on the radio was assumed, not measured.** The project assumes a radio
    listener in 94122; it does not model KNBR's night-time skywave, the 104.5 FM
    contour over the Sunset, or whether an indoor radio picks up KTCT.

### Larger

11. **No automated freshness check.** Every source here was read by hand on 2026-09-20.
    A scheduled re-fetch with a diff report would turn IR-24 and IR-23 into tickets
    instead of surprises.
12. **The bundle contains 429 occupancy records plus a 272-game NFL reference slate.**
    The generated JSON/JS is larger because the reference rows are deliberately visible;
    a per-date or per-month lazy load would help on mobile.
13. **Parity variants are now batched.** The harness runs all four scope/frame variants
    in one Node process instead of spawning Node four times. The remaining cost is the
    date sweep itself, not repeated startup.
14. **No screenshot or visual test.** `tests/render_check.js` asserts the DOM, not the
    layout, so a CSS regression that hides the scope picker would still pass.

---

# Part 5 (revision 2026-09-20) — invariants added in this pass

| Invariant | Test |
|---|---|
| Section definitions are the ones the request asked for | `TestCoverageSections::test_section_definitions_match_the_request` |
| Free minutes are monotonic across sections (1 ≥ 2 ≥ 3) | `TestCoverageSections::test_section_filter_is_monotonic` |
| A date inside an MLB season frame is never read free | `TestMlbSeasonFrameFallback::test_in_season_date_without_per_game_data_is_blocked` |
| The frame fallback fires on the days it is supposed to | `TestMlbSeasonFrameFallback::test_frame_fallback_actually_blocks_something` |
| No 7-day run exists inside the NFL season | `TestWeekWindowInvariant::test_no_week_long_run_inside_the_nfl_season` |
| JS and Python agree for every section, with and without frames | `TestJsPythonParity::test_scope_1_matches_exactly` etc. |
| No date carrying a game in a section reads free in that section | `TestJsPythonParity::test_no_date_is_free_when_a_game_exists_in_its_section` |
