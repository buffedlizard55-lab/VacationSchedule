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

---

## Part 2 — Data gaps, ranked by impact (updated 2026-09-20)

### 1. MLB 2026 postseason first pitch times do not exist (HIGH — resolves itself)

Round dates official (Wild Card Sep 29–Oct 1, Division Series Oct 3–10, LCS Oct 11–20,
World Series Oct 23–31); **matchups and times are still TBD** (API serves placeholder
teams + `07:33:00Z` sentinel). Clinched so far (as of 2026-09-19): Rays, Brewers,
Dodgers, Yankees, Braves. **Re-run the live fetch after 2026-09-27** — the bracket will
fill and the code already handles it via the live `statsapi.mlb.com` call.

### 2. NFL Week 18 (49ers @Cardinals) date still TBD (MEDIUM — resolves itself)

The NFL sets Week 18 dates/times near season's end. Falls in the 2027-01-09/10 window.

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

## Part 4 — Suggested work for the next session

Ordered by value per unit of effort.

### Quick wins

1. **Re-fetch MLB postseason times after 2026-09-27** (and verify the CBA outcome for
   2027). Highest-value.
2. **Re-check Stanford/Cal kickoff announcements** ~2 weeks before each game.
3. **Fetch the full Earthquakes fixture list** and the A's 2027 radio plan.
4. **Re-verify 2027 Pro Bowl date** once the NFL publishes it (currently ESTIMATED).

### Medium

5. **Add NBA and NHL** (Warriors, Sharks) — scope decision needed.
6. **Add college basketball** (Stanford, Cal, USF on KNBR). Directly undercuts the
   February recommendations; important for honesty.
7. **Model bowl games / CFP** once assignments are known (mid-Dec 2026).
8. **Add Westwood One playoff schedule** for January 2027 once published.

### Larger

9. **Confidence score per day** from `unconfirmed_minutes` / `has_unconfirmed_times`.
10. **Weekly/monthly calendar view** (engine already computes per-day reports).
11. **Over-the-air reception modelling** (KNBR 680 50 kW vs 104.5/107.7 FM contours).
12. **Automated freshness checks** with a schedule re-fetch + diff report.

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
