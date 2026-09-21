# Method and confidence model

## Scope

Sections 1, 2 and 3 are nested sets of tags from `data/verified/profiles.json`.
MLB means all clubs regardless of local radio availability, as requested. The NFL
portion is the 49ers plus Westwood One national feeds; the full NFL regular-season
slate is separately displayed as reference. Extra tracked national NCAA games
belong to `all`, not silently to Sections 1–3.

Since the 2026-09-21 pass, `all` also carries the other verified Bay Area
live-radio sports the request asked for as high-priority busy time: the Golden
State Warriors (NBA) and Golden State Valkyries (WNBA) on KGMZ 95.7 The Game.
They are **deliberately outside Sections 1–3**, whose definitions are the user's
verbatim words ("just the following set of games"). Only AM/FM broadcasts block:
Valkyries games the club lists as Audacy-app-only and the San Jose Sharks
(app/streaming only, no Bay Area flagship) are disclosed exclusions. The wider
scope is still not exhaustive — USF basketball on KNBR, Westwood One NCAA
basketball and local college basketball remain documented gaps in
`data/verified/other_radio_sports.json`.

**Affiliation ≠ carriage ≠ reception.** A national broadcast listing and an
affiliate list do not prove that the game airs locally. A streaming link is not
an AM/FM station. HD-2 requires an HD receiver. No signal strength at a 94122
address has been measured by this project.

## Season blocking: exact fixtures before envelopes

Since the CI refresh committed `data/verified/mlb_schedule_2026.csv` and
`_2027.csv`, **2026 and 2027 are analysed from the league's own fixture dates**.
`mlb_fixture_days(year, strict)` reads the CSV and returns every date with a game:
regular season (`R`), the All-Star Game (`A`) and the postseason rounds (`F`, `D`,
`L`, `W`, plus legacy `P`, `C`) always count; Spring Training (`S`) and pre-season
exhibition rows (`E`) count under the strict reading only. `blocked_days_for_year()` records which mode it used in
`mlb_block.mode` (`exact_fixtures` or `season_frame`) and the block's start/end,
count, source and — for 2027 — the announced Opening Night anchor (see IR-39).

Measured from the committed snapshots: 2026 has 2973 fixtures (2430 regular season,
451 Spring Training, 53 postseason placeholders, 38 exhibition, 1 All-Star) from
2026-02-20 to 2026-10-31; 2027 has 2900 (2430 regular season, 465 Spring Training,
4 exhibition, 1 All-Star) from 2027-02-19 to 2027-09-26, plus the announced
2027-03-24 Opening Night. Both files are re-validated on every run: 30 clubs present,
regular-season count in range, every club at 162, unique game ids.

Inside the regular season the league schedules **no game at all** on 2026-07-13,
2026-07-15 and 2027-07-12, 2027-07-14, 2027-07-15 (the All-Star break; the 2026
All-Star Game itself is on 2026-07-14 and the 2027 one on 2027-07-13). Those dates
are free of MLB by measurement, not by assumption — but they are single days inside
a busy corridor, so they do not create a vacation window on their own.


The two modes are:

* `exact_fixtures` — the committed official snapshot for that year
  (`data/verified/mlb_schedule_<year>.csv`) lists every game the league has scheduled.
  Only real fixture dates are blocked, so a date with no row is free of MLB under the
  chosen reading (plus the announced-anchor dates in `mlb_block.anchors`).
* `season_frame` — no snapshot exists for that year, so the published season window
  (Spring Training → postseason end, or first regular game → postseason end under the
  regular-season reading) is blocked continuously. Conservative, and it can hide real
  breaks. 2028 and 2029 are in this mode until the league releases those schedules.

Reading detail: the strict reading is "any game the league schedules for its clubs",
so Spring Training and the pre-season exhibition rows block too. The regular-season
reading is "regular season plus the All-Star Game plus the postseason", so those
exhibition rows do not block by themselves. No time is inferred anywhere in this step:
a row with no published first pitch still blocks the whole local date through the TBD
envelope described below.

## Daily intervals

1. Convert scheduled start and any known earlier radio airtime to UTC.
2. Estimate the end from kickoff/first pitch plus the planning duration. Halftime
   is included, not treated as free time or added twice.
3. With a known date but missing kickoff (including null timestamps and the MLB
   `07:33:00Z` sentinel), reserve **00:00 to next local midnight**. This supersedes
   the old afternoon-only envelopes, which falsely exposed morning free time.
4. Skip source-identified cancelled/postponed original fixtures; future rescheduling
   still requires refreshed official data. Do not guess a replacement date.
5. Clip every interval to the selected day's bounds, merge overlapping or adjacent
   intervals, then report their complement. Games 1–5 PM and 8–10 PM leave 5–8 PM.
6. If MLB is in a season frame but no fixture coverage exists, reserve that whole
   local date. The old bug marking September 20–27 as complete merely because the
   postseason snapshot was retrieved September 20 is fixed: postseason coverage
   begins September 28, not the retrieval date.
7. The day board classifies each date from the same committed lists: a date inside a
   season's fixture span is busy if the league has a game that day and **free of MLB**
   if it has none (the All-Star break shows up as free), while dates beyond the
   committed span stay reserved until the league publishes them.
8. If the browser cannot reach statsapi.mlb.com, the day board falls back to the
   committed season snapshot for that date (official dates and matchups, no live
   status) and says so in the note. It never silently shows an empty day.
9. An unblocked day is presented as **NO KNOWN CONFLICT**, never certified free.
   Other league coverage remains incomplete. Exact elapsed minutes are a calculation
   on the available inputs, not proof of accurate broadcast ending times.

Both Python and JavaScript implement the interval model. Parity tests compare
all bundled dates/scopes. Arithmetic uses UTC; display uses `America/Los_Angeles`.
March 8, 2026 has 1,380 minutes and November 1 has 1,500. “PST” is used only in
winter; the summer abbreviation is PDT. Today is determined in Pacific Time,
not from the browser's UTC date.

## Planning durations (not current-season verified averages)

| League | Minutes | Interpretation |
|---|---:|---|
| MLB | 164 | Planning estimate. Official historical 2025 nine-inning figure is 158 minutes; see Sources. |
| NFL | 192 | Planning estimate including halftime. |
| NCAAF | 204 | Planning estimate including halftime. |
| MLS | 120 | Planning estimate including halftime/stoppage. |
| NBA | 150 | Planning estimate. Secondary 2025-26 tip-to-buzzer references ≈ 2:18-2:19; see Sources (2026-09-21). |
| WNBA | 120 | Planning estimate. Secondary references ≈ 1:45-2:00 for a 40-minute game. |

No duration guarantees against overtime, extra innings, weather, extended
pregame or postgame coverage. Where only Westwood One airtime is known and no
matching official NFL kickoff exists, a disclosed **90-minute allowance** is
added. It is a planning assumption, not an invented official kickoff.

## Vacation candidates

For each calendar year, section and Spring Training choice, the model reserves:

- The previous NFL season's final weeks/playoff dates and Pro Bowl; future dates
  are templates, not released schedules.
- MLB continuously from spring training (strict) or the **first** regular-season
  game, through the postseason frame. March 24, 2027 Opening Night counts.
- The current NFL season continuously from its preseason anchor through December.
- In Sections 2–3, college season and conditional bowl/CFP envelopes. The old
  January 11 cutoff was too early: 2026–27 extends through January 25. Future
  title dates are fourth-Monday-in-January estimates, not confirmed schedules.
- In Section 3, MLS envelopes. From 2027: February 1–May 31 and July 1–December 15.
  Official format is summer–spring; those exact envelope boundaries are assumptions.
- In `all` only, Warriors NBA and Valkyries WNBA envelopes: the verified 2026-27 /
  2026 frames where they exist, otherwise estimated mid-October→mid-April and
  May→September envelopes with conditional playoff tails. Envelopes hide rest
  days; that is why the `all` scope now reports no free run at all while the
  three requested sections are unchanged.

The complement yields inclusive start/end dates and 7/14/21-day checks. Continuous
frames are **conservative and can hide real breaks**, particularly for a single
club, bye weeks and the MLS transition. A negative result means no candidate
found by this model, not a mathematical proof that a week without games is
impossible. School qualification, flex scheduling and unreleased future calendars
can alter the result. “Free days in year” is likewise a model count, not a fixture census.

## Refresh behavior

- Daily Pages builds attempt `scripts/refresh_mlb.py`. Downloads are atomic and
  reject empty/incomplete responses, requiring all 30 regular-season clubs and
  at least 2,400 records. These checks detect obvious truncation, not every possible
  source error. Offline builds and tests need no external connection.
- The published artifact includes refreshed MLB rows but is not committed by the
  workflow. Refresh status is published separately; failure leaves the available
  offline data and explicit warning rather than erasing it.
- Online daily fetching includes neighboring official dates, so PT conversion and
  games running beyond midnight are handled. New per-date data replaces stale
  aggregate rows rather than adding duplicates. Older asynchronous requests cannot
  overwrite the currently selected day's result.
- An empty future API response never establishes a released, game-free season.
- The vacation model still uses season frames, not a full refreshed fixture scan.
  Making trip analysis fixture-driven is a next-session priority.
