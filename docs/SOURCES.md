# Source register and verification boundaries

Review date: **2026-09-20, Pacific Time**. This replaces the earlier source register's
blanket verification assertions. A URL is not proof that every field in a snapshot
was independently rechecked. The app's inherited `VERIFIED` fields describe the
original snapshot's attribution, not a new audit of every row.

## Opened during the Pages review

| Primary source | What was observed | What it does NOT prove |
|---|---|---|
| [MLB 2026 season API](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2026) / [range query](https://statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029) | Range response returned a 2026 frame, spring February 20, regular season March 25–September 27, postseason frame ending October 31. | A range response is not evidence that every other year is unpublished; individual year queries are necessary. |
| [MLB 2027 season API](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2027) | Published season frame; spring February 19; full Opening Day March 25. | Exact postseason fixtures or every kickoff. |
| [MLB 2027 spring release](https://www.mlb.com/press-release/press-release-mlb-announces-2027-spring-training-schedule) | Extracted official text says Opening **Night March 24**, followed by full Opening Day March 25. | Fetch tool resolved to an unrelated MLB article URL while retaining release text; redirect irregularity remains flagged. |
| [MLB 2028 API](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2028) and [2029 API](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2029) | Both individual queries returned `seasons: []`. | Absence in one API is not proof that no announcement exists anywhere; these years remain estimates pending a released schedule. |
| [MLB club list](https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2026&fields=teams,id,name) | All 30 names/IDs stored in `mlb_clubs.json`; Giants 137 and Athletics 133. | Local carriage of all 30 teams. |
| [MLB playoff picture](https://www.mlb.com/news/mlb-playoff-picture-and-bracket-2026) | Extracted text lists Rays, Brewers, Dodgers, Yankees, Braves **and Red Sox** as clinched. Added Boston. | Seeding, specific matchups, or first-pitch times. Link extraction redirected to a related article; no matchup inferred from a berth. |
| [Westwood One NFL schedule](https://www.westwoodonesports.com/nfl-schedule/) | All four extracted chunks reviewed. Corrected Giants–Rams September 21 airtime to **7 PM ET**, previously 8 PM. Retained national-feed fixtures and TBA slots. | Local station selection and kickoff time. Airtime is not kickoff. The page is dynamic, not a historical complete-season archive. |
| [Westwood One station finder](https://www.westwoodonesports.com/station-finder/) | Explicit warning: local blackouts/programming conflicts mean not every affiliate airs every broadcast. | Per-game KNBR/KTCT availability. HD subchannels require HD-capable equipment, not an ordinary analog receiver. |
| [Athletics radio affiliates](https://www.mlb.com/athletics/schedule/watch) | KNEW 960 AM listed for Bay Area, KSTE 650 AM for Sacramento. | KNBR carriage for A's; the old live-fetch assignment was wrong. |
| [NFL Super Bowl LXIII announcement](https://www.nfl.com/news/las-vegas-to-host-super-bowl-lxiii-in-2029) | Las Vegas/Allegiant Stadium and 2029 are official. | No exact date in the reviewed text. February 11 is now labelled **ESTIMATED**. |
| [MLS calendar announcement](https://www.mlssoccer.com/news/mls-to-align-calendar-with-top-leagues-around-world) | February–May 2027 transition; July 2027–May 2028 season; mid-December–early-February break, no January league games. | Exact Earthquakes fixtures. Whole-month planning envelopes are conservative estimates. |
| [CFP schedule request](https://collegefootballplayoff.com/sports/2019/5/23/schedule.aspx) | Redirected to `/404`, but official site's schedule widget lists January 25, 2027 title game. | Successful canonical schedule retrieval, school qualification or future title dates. Use [CFP home](https://collegefootballplayoff.com/) for follow-up. |

## Duration research

MLB's official report gives **2:38 for nine-inning games through September 25,
2025**, not 2026. [1](https://www.mlb.com/news/mlb-average-game-time-under-three-hours-third-straight-year)

The engine retains conservative planning lengths of MLB **164**, NFL **192**,
NCAAF **204**, and MLS **120** minutes. These are **assumptions**, not independently
verified 2026 league averages. Halftime is already included, not an additional
free interval. Historical secondary references used by the earlier project:

- https://www.profootballnetwork.com/how-long-is-a-football-game-breaking-down-the-time-between-the-first-and-last-whistle/
- https://tickpick.com/blog/how-long-are-mls-games/

Do not use these durations as guaranteed broadcast finish times. Unknown WW1
kickoff with known airtime gets a separately disclosed 90-minute planning allowance;
when the official NFL snapshot matches a fixture, its kickoff anchors the end estimate.

## Inherited inputs — source-linked, NOT all independently rechecked this pass

| Input | Primary reference | Remaining validation |
|---|---|---|
| 272-game NFL regular season | [NFL release](https://www.nfl.com/nfl-schedule-release/) and [by-week PDF](https://media.nfl.com/content/dam/communications/football-communications/2026/news/05%2014%2026%20-%202026%20NFL%20Schedule%20-%20By%20Week.pdf) | Parser checks 272 unique matchups and 17 appearances per club. These invariants do not verify every date/opponent against the PDF. Reconcile automatically next session. |
| 49ers fixtures | https://www.49ers.com/schedule/ | Refresh preseason, flex selections and conditional playoff participation. |
| Stanford / California | https://gostanford.com/sports/football/schedule and https://calbears.com/sports/football/schedule | Refresh kickoff announcements and radio assignments. |
| Earthquakes | https://www.sjearthquakes.com/schedule/ | Offline fixtures incomplete; cup competitions not comprehensively ingested. |
| MLB postseason date holds | https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31&gameType=E,S,D,L,F,W | Existing per-date holds retained. Daily all-club refresh can replace aggregate placeholders with official fixture rows. |
| NFL postseason calendar | https://www.seahawks.com/news/nfl-announces-important-dates-for-2026-2027 | Inherited key dates retained; future templates remain estimates. |
| 2026 Pro Bowl | https://operations.nfl.com/updates/the-game/2026-pro-bowl-games-presented-by-verizon-moved-to-tuesday-of-super-bowl-lx-week-in-bay-area/ | Event date does not establish local AM/FM broadcast. Conservatively reserved. |
| Local radio affiliation | https://www.cumulusmedia.com/2026/04/15/san-francisco-49ers-announce-multi-year-partnership-extension-with-cumulus-medias-knbr/ | Per-game carriage, conflicts and actual 94122 reception not measured. |

## Retrieval limitations

Direct Python and curl requests for the full MLB schedule failed TLS connection
setup in the sandbox. No complete full-season file was fabricated. The scheduled
GitHub Actions refresh records success/failure on the published site. Successful
fixture downloads do not automatically validate unrelated inherited datasets.
