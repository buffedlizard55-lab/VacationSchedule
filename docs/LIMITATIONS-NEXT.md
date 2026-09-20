# Limitations and suggested next work

Written for the next session. Everything here is a real gap, not a hypothetical.

---

## Part 1 — The honest headline limitation

### There is no window in any year with zero live Bay Area sports radio

The site answers the question **as scoped**: no MLB, no 49ers, no Earthquakes, no
Stanford NCAAF, no Cal NCAAF. Under that definition, real windows exist.

But a listener in the Outer Sunset with a standard AM/FM radio on a "free" day will
still hear live sports. **Not covered by this project:**

| Sport | Team(s) | Season | On KNBR? |
|---|---|---|---|
| NBA | Golden State Warriors | Oct – Jun | No (other outlets) |
| NHL | San Jose Sharks | Oct – Jun | No (other outlets) |
| NCAA basketball | Stanford, Cal | Nov – Mar | **Yes** |
| NCAA basketball | USF men's | Nov – Mar | **Yes** |
| High school / other | various | varies | sometimes |

**This matters most for the February windows this project recommends.** Mid-February
is the peak of the college basketball season, and KNBR carries Stanford, Cal and USF.
A "free" day in February 2029 will almost certainly have live college basketball on
KNBR.

**Nothing in this repo should be read as "no sports radio."** It means "none of the
five sports you listed."

---

## Part 2 — Data gaps, ranked by impact

### 1. 49ers Weeks 1, 2, 8 and all preseason games are missing (HIGH)

The `49ers.com` retrieval did not capture them. Those dates read **free** when games
occur. Week 18 is `TBD` (vs Arizona at State Farm, inside the 2027-01-06 → 2027-01-12
window).

**These are labelled in `unresolved` but not conservatively blocked**, because no
date is known. That is the one place the project knowingly reports a possibly-wrong
"free".

**Fix:** pull from a live NFL feed, e.g.
`https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/sf/schedule`.

### 2. 11 of 24 Stanford/Cal games are envelope-blocked (MEDIUM)

Real dates, no announced kickoff. Blocked 11:00–23:59 PT. This **over-blocks**: some
genuinely free afternoons read busy. Conservative by design, but it understates free
time.

**Fix:** re-check `gostanford.com` and `calbears.com` closer to game day; times are
typically announced ~2 weeks out.

### 3. Earthquakes February–July fixtures were never retrieved (MEDIUM)

Only 2026-08-01 onward is in the snapshot. Mitigated because MLB Spring Training
already blocks those dates, so no vacation window is affected — but MLS-only analysis
is incomplete.

### 4. Matchday 33 (2026-10-31, vs Real Salt Lake) has no kickoff (LOW)

Envelope-blocked. Subsumed by the NCAAF envelope that day anyway.

### 5. Bowl games are not modelled (MEDIUM)

Stanford and Cal bowl assignments are undetermined. Bowls run roughly 2026-12-19 →
2027-01-01, with the CFP National Championship on **2027-01-11** at Allegiant Stadium.
Late-December dates may be under-blocked.

### 6. MLB per-game times are fetched live, not stored (LOW, by design)

**Fixed.** The bundle now carries all **187 regular-season date markers** (217 MLB rows
total), so the snapshot alone answers "is 2026-06-14 free?" with a correct *no*. Each
marker blocks the regular-season playout envelope 10:00-23:59 PT; the app supersedes it
with live per-game times. See IR-17.

### 7. Radio affiliates partly unconfirmed (MEDIUM)

- **Westwood One's SF affiliate** — presumed KNBR, **not verified**.
- **The Athletics' Bay Area flagship** — **not identified**.
- **KZSU 90.1** (Stanford) and **KGO 810** (Cal) — plausible, **not confirmed** for 2026.

### 8. Durations are industry averages, not league statistics (LOW)

MLB 164 min, NFL 192, NCAA 204, MLS 120. Sourced from blogs, not leagues. Rain delays
and extra innings are unknowable in advance, so **free time at the tail of a game is
optimistic.**

---

## Part 3 — What could not be resolved at all

### MLB 2026 postseason first pitch times

**They do not exist.** Round dates are official (Wild Card Sep 29–Oct 1, Division
Series Oct 3–10, LCS Oct 11–20, World Series Oct 23–31), but the Stats API serves
placeholder teams and a fabricated `gameDate` of `...T07:33:00Z`.

As of 2026-09-19 the clinched teams were Rays, Brewers, Dodgers, Yankees and Braves —
**but matchups were still TBD**, so no time can be derived even in principle.

**This will resolve itself** as the bracket fills. Re-run the live fetch after the
regular season ends 2026-09-27.

### 2027–2029 schedules

Unreleased. `statsapi.mlb.com/api/v1/seasons` returns 2026 only — that is MLB's own
machine-readable statement that the seasons do not exist. Everything for those years
is `ESTIMATED` with a `basis` field.

### Super Bowl LXIII's date

Las Vegas is confirmed; the date is not. Estimated 2029-02-11 (second Sunday).
**This single unconfirmed date sets the best 2029 window** — see IR-12 for the
sensitivity range (0 to 14 days).

---

## Part 4 — Suggested work for the next session

Ordered by value per unit of effort.

### Quick wins

1. **Fill the 49ers gaps** (Weeks 1, 2, 8, preseason, Week 18) from a live ESPN NFL
   feed. Highest-value fix — it closes the only known false "free".
2. **Re-fetch MLB postseason times after 2026-09-27.** The data will exist then; the
   code already handles it via the live fetch.
3. **Re-check Stanford/Cal kickoff announcements** ~2 weeks before each game to
   replace envelope blocks with real times.
4. **Verify Westwood One's SF affiliate** and identify the A's flagship. Two phone
   calls or one call to Cumulus.

### Medium

5. **Add NBA and NHL** (Warriors, Sharks). Requires deciding whether they are in scope
   — the user listed five sports, but Part 1 above shows why the distinction matters.
6. **Add college basketball** for Stanford, Cal and USF on KNBR. This directly
   undermines the February recommendations.
7. **Model bowl games** once assignments are announced (mid-December 2026).
8. **Fetch the Earthquakes' full-season fixture list**, not just August onward.

### Larger

9. **Add a "confidence" score per day** combining: how many sources cover it, how much
   of the busy time is envelope vs confirmed, and how far in the future the date is.
   The raw fields already exist (`unconfirmed_minutes`, `has_unconfirmed_times`).
10. **A weekly/monthly calendar view** rather than only day-by-day. The engine already
    computes per-day reports; this is a rendering task.
11. **Over-the-air reception modelling.** KNBR 680 is 50 kW non-directional from San
    Francisco, so Outer Sunset coverage is strong, but 104.5 FM and 107.7 FM have
    different contours. A signal-strength overlay would make "receivable on a standard
    AM/FM radio" precise rather than assumed.
12. **Automated freshness checks.** Sources were retrieved 2026-09-20 and will rot.
    A scheduled re-fetch with a diff report would keep the snapshot honest.

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
| JS and Python agree to the minute on all 265 dates | `test_day_reports_match_exactly` |
| Estimated seasons are never labelled verified | `test_2027_2029_strict_windows` |

**Two rules worth repeating:**

- Always `.astimezone(timezone.utc)` before subtracting or comparing aware datetimes.
  CPython silently returns wall-clock time when both sides share a `tzinfo`. See IR-14.
- An un-timed game must **block**, not vanish. Returning `None` is how a Wild Card day
  got reported as free. See IR-16.
