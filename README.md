# VacationSchedule · Bay Area vacation planner

**[Open the GitHub Pages site](https://buffedlizard55-lab.github.io/VacationSchedule/)**

Compare three definitions of sports-free vacation time in **2026–2029**, with
one-, two- and three-week trip checks, a daily scoreboard, a month calendar,
Pacific-time free intervals, sources, and a review queue.

## The three sections

| Section | What counts as busy |
|---|---|
| **1 · MLB + NFL radio** | All 30 MLB clubs; Giants and Athletics high priority. 49ers preseason, regular season and postseason, high priority. Westwood One national NFL feeds, high priority. |
| **2 · Add Stanford / Cal** | Everything in Section 1, plus Stanford and California football, high priority. |
| **3 · Add Earthquakes** | Everything in Section 2, plus San Jose Earthquakes MLS, high priority. |

The additional “Everything tracked” option includes national NCAA football. It
**does not mean every sport on every Bay Area station**. Other sports remain a
coverage gap, not silently verified free time.

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
2029's February 11 Super Bowl date is an **estimate**: the NFL host announcement
reviewed confirms Las Vegas and the year, not the exact day.

With Spring Training included, no modeled section reaches two weeks. Adding the
Earthquakes removes the future February corridor in this conservative model:
MLS announced a February–May 2027 transition followed by summer–spring seasons.
A continuous season envelope can hide real fixture gaps; “none found” is **not**
a proof that a trip is impossible. See [the complete generated report](docs/VACATION-WINDOWS.md).

## Data honesty and current coverage

- **No blanket “fully verified” claim.** The bundled inputs are partly inherited
  snapshots. This review did not independently re-fetch and compare every NFL,
  college or MLS fixture. See [the source audit](docs/SOURCES.md).
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
Pages must use **GitHub Actions** as its build source. All site assets and health
requests are relative so the `/VacationSchedule/` project path works.

## Review and next work

The three-pass review, source corrections, tests and environmental limitations
are recorded in [REVIEW-PAGES-2026-09-20.md](docs/REVIEW-PAGES-2026-09-20.md).
The next session should prioritize [LIMITATIONS-NEXT.md](docs/LIMITATIONS-NEXT.md):
per-game local radio carriage, complete college/MLS fixtures, additional local
sports, all-team NFL preseason, and automated source reconciliation.
