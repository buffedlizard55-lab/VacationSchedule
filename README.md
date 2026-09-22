# VacationSchedule · Bay Area vacation planner

**[Open the GitHub Pages site](https://buffedlizard55-lab.github.io/VacationSchedule/)**

Compare three definitions of sports-free vacation time in **2026–2029**, with
one-, two- and three-week trip checks, a daily scoreboard, a month calendar,
Pacific-time free intervals, sources, and a review queue.

Two tabs added in the 2026-09-21 session-3 pass answer the other half of the
request:

| Tab | What it shows |
|---|---|
| **MLB 2026 & 2027** | Every fixture the league has scheduled, all 30 clubs: Spring Training, regular season, All-Star Game and postseason, from the committed Stats API snapshot. Filter by club, month or game type; Giants and Athletics rows are highlighted. Each row carries the league's `game_pk`. |
| **Postseason 2026** | The postseason split into what is resolved and what is not: clinched berths and division titles from MLB's tracker, the official round dates, the dates that cannot carry a game, and a machine-measured count of how many first pitches the league has published (still zero). |

The *Plan a trip* tab now opens with an answer matrix: one row per year, one
column per section, both Spring Training readings, and which trip lengths fit.

## The three sections

| Section | What counts as busy |
|---|---|
| **1 · MLB + NFL radio** | All 30 MLB clubs; Giants and Athletics high priority. 49ers preseason, regular season and postseason, high priority. Westwood One national NFL feeds, high priority. |
| **2 · Add Stanford / Cal** | Everything in Section 1, plus Stanford and California football, high priority. |
| **3 · Add Earthquakes** | Everything in Section 2, plus San Jose Earthquakes MLS, high priority. |

The additional “Everything tracked” option includes national NCAA football plus
the **other verified Bay Area live-radio sports** added at the user's request:
Golden State Warriors (NBA) and Golden State Valkyries (WNBA) on KGMZ 95.7 The
Game, flagged high priority. Only AM/FM broadcasts count: the San Jose Sharks
(app/streaming only — no Bay Area flagship) and Audacy-app-only Valkyries games
are disclosed exclusions. This scope still **does not mean every sport on every
Bay Area station** — USF basketball on KNBR, Westwood One NCAA basketball and
local college basketball remain documented gaps, not silently verified free time.

## What can I book?

**These are planning candidates, not booking guarantees.** Official fixtures,
estimated lengths, conditional postseason holds and unreleased-season estimates
are different kinds of evidence. Station affiliation does not establish local
carriage of every game or reception at a particular address in 94122.

With **Spring Training excluded**, Sections 1 and 2 have these longest modeled
windows:

| Year | Candidate dates (inclusive) | Days | Fits 1 / 2 / 3 weeks? |
|---|---|---:|---|
| 2026 | February 9 – March 24 | 44 | Yes / Yes / Yes — **past** |
| 2027 | February 15 – March 23 | 37 | Yes / Yes / Yes |
| 2028 | February 14 – March 24 | 40 | Yes / Yes / Yes — estimated |
| 2029 | February 12 – March 24 | 41 | Yes / Yes / Yes — estimated |

2027 MLB Opening Night is **March 24**, so it is not part of that vacation window.
2027 NFL round/Pro Bowl assumptions still make that year's result provisional.
Super Bowl LXIII (Allegiant Stadium, 2029) host and year are official, but the exact
day is **estimated** at February 11, 2029: secondary sources conflict (WJHL/KLAS
reports Feb 11 announced; NBC says no firm date; the league's own release names no
day). Super Bowl LXIV in 2030 is likewise an estimate. See IR-12.

With Spring Training included, no modeled section reaches two weeks. Adding the
Earthquakes removes the future February corridor in this conservative model:
MLS announced a February–May 2027 transition followed by summer–spring seasons.
A continuous season envelope can hide real fixture gaps; “none found” is **not**
a proof that a trip is impossible. See [the complete generated report](docs/VACATION-WINDOWS.md).

## How the official fixture lists get into the repo

`data/verified/mlb_schedule_<year>.csv` and its `_summary.json` are produced by
`scripts/export_mlb_schedule.py`, which runs on the GitHub runner (the development
sandbox cannot open TLS to statsapi.mlb.com). The workflow refreshes the 2026 and
2027 seasons, validates them (all 30 clubs present, plausible regular-season
count, unique game ids), commits the compact CSV + provenance summary back to the
branch and uploads the raw payloads as an artifact. The summary records the exact
request URL, the retrieval time and a SHA-256 of the raw response, so every row is
re-verifiable by hand. `data/verified/mlb_postseason_state_<year>.json` is the same
idea for the postseason: it counts game records, published first pitches, reserved
dates and impossible dates instead of asserting them.

When a season snapshot is committed, the vacation analysis blocks real fixture
dates (`mlb_block.mode = exact_fixtures`) instead of a continuous season frame. Both
2026 and 2027 are in that state now: 2973 and 2900 fixtures, re-validated on every
run (30 clubs, 2430 regular-season games each, every club at 162, unique game ids).
The MLB tab carries each fixture's league `game_pk`, and the season files name the
dates inside the regular season that carry no game at all (the All-Star break).

## Data honesty and current coverage

- **No blanket “fully verified” claim.** The bundled inputs are partly inherited
  snapshots. The 2026-09-21 line-by-line pass re-verified the Westwood One rows,
  MLB clinch facts, Super Bowl dates, the MLB API year frames, and the new
  Warriors/Valkyries/Sharks findings; a session-2 pass the same day re-verified
  the 49ers schedule including per-game radio stations, the Athletics home venue
  (Sutter Health Park, Sacramento), and the live Stats API state (2026/2027
  frames; 53 postseason records still without published times; six clinched
  berths). The 2026-09-22 pass re-read every primary
  source again and corrected four data errors it found: the Super Bowl LXIII
  exact day is back to ESTIMATED (secondaries conflict; league release names no
  day), the Earthquakes are backfilled to the full 34-match schedule with an
  Aug 1 kickoff correction, one Valkyries radio flag was fixed, and the CFP
  title-game note was corrected to January 25, 2027. College fixtures remain
  inherited snapshots with one dead source URL replaced. Its second pass also
  made conditional coverage visible on the day board: free days inside a
  bowl/CFP/MLS-Cup envelope name it, and the ACC Championship block is flagged
  as conditional on Stanford/Cal qualifying (IR-47). See
  [the source audit](docs/SOURCES.md) and [the 2026-09-22 review](docs/REVIEW-2026-09-22.md).
- MLB all-club **per-day online fetching** is available. The checked-in offline
  bundle has postseason date holds, not every 2026 regular-season game.
- A daily Pages workflow attempts an **all-club 2026 MLB snapshot**. It validates
  at least 2,400 regular-season records and all 30 clubs before accepting it.
  A failed refresh is visible in the site; it never turns an empty future feed
  into verified free time. Deployment artifacts contain the refreshed data;
  the workflow does not push changes to a branch.
- The **272-game NFL regular-season reference** is retained, with flexible fields
  left TBD. It is not 272 Bay Area radio broadcasts, nor a complete all-team
  preseason archive. Only the requested section's events and conservative
  radio backstops enter the daily busy calculation.
- MLB clinched berths are not substituted for unannounced playoff matchups or
  first-pitch times. The reviewed playoff picture now includes Boston's berth.
- **TBD kickoff = entire local date reserved**, including DST's 23/25-hour days.
  A null start time with a known date cannot disappear from the engine.
- “No known conflict” describes the snapshot, not a certified quiet day. Game
  ends remain estimates; overtime, weather and station pre/postgame can overrun.
- All times use **America/Los_Angeles**, automatically PST or PDT, not fixed UTC−8.

## Run locally

```sh
npm ci
npm run build
npm test
python3 -m unittest discover -s tests
python3 -m http.server 8080 --bind 0.0.0.0 --directory site
```

The static site works without a server-side API. It retains its offline fallback
when cross-origin MLB requests fail. No credentials or user data entry required.

Optional full MLB refresh (network required):

```sh
python3 scripts/refresh_mlb.py
npm run build
```

## GitHub Pages

`.github/workflows/pages.yml` tests pull requests and publishes **`site/`**, not the
repository root, on pushes to `main`. It also attempts a daily MLB refresh and can
be run with **Actions → Test and publish vacation planner → Run workflow**.
For artifact deployment, Pages should use **GitHub Actions** as its build source.
The existing legacy `main`/root setting also works: root `index.html` forwards to
`site/`, with `.nojekyll` disabling Jekyll processing. This fallback does not need
an administrator settings change but uses the checked-in partial data rather than
the workflow’s refreshed artifact. Assets and health requests are relative, so
both `/VacationSchedule/` and `/VacationSchedule/site/` work.

## Review and next work

The three-pass reviews, source corrections, tests and environmental limitations
are recorded in [REVIEW-PAGES-2026-09-20.md](docs/REVIEW-PAGES-2026-09-20.md) and
[REVIEW-2026-09-21.md](docs/REVIEW-2026-09-21.md). The next session should
prioritize [LIMITATIONS-NEXT.md](docs/LIMITATIONS-NEXT.md): resolving MLB
postseason times as they publish (from 2026-09-27), Valkyries playoff radio and
later rounds, the Warriors grid row-count discrepancy, per-game local radio
carriage, complete college/MLS fixtures, and automated source reconciliation.
