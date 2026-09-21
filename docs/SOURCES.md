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

## Re-verified 2026-09-21 (line-by-line pass)

| Primary source | What was observed | What it does NOT prove |
|---|---|---|
| [Westwood One NFL schedule](https://www.westwoodonesports.com/nfl-schedule/) | All four page chunks re-read. **All 71 rows in `nfl_westwoodone_2026.json` match the live page line by line** (matchup, date, ET air time, feed name, TBA slots, event IDs). No new or changed rows since the 2026-09-20 snapshot. (Session 2 correction: the file's own meta miscounted the rows as 70; the count is 71 — 1 NCAA + 70 NFL rows. The NCAA row is listed here for the line-by-line record: LSU@Ole Miss 09-19 19:00 ET.) | Local carriage per game; kickoff times (air time ≠ kickoff). |
| [Westwood One NCAA football](https://www.westwoodonesports.com/ncaa-football/) | Upcoming grid matches the bundled NCAAF rows (OU@Georgia 9/26 3:00pm ET; ND@UNC 10/3, Indiana@Nebraska 10/10, Penn State@Michigan 10/17, Ole Miss@Texas 10/24, Florida@Georgia 10/31 3:00pm, Oregon@Ohio State 11/7, Michigan@Oregon 11/14, LSU@Tennessee 11/21, Michigan@Ohio State 11/28 11:30am; the SEC Championship and Army-Navy rows come from the network's event grid). | Whether KNBR airs every one of them (affiliate conflict warnings stand). |
| [MLB clinch tracker](https://www.mlb.com/news/2026-postseason-teams) | Six berths: Rays 9/11, Brewers 9/11, Dodgers 9/14, Yankees 9/14, Braves 9/18, Red Sox 9/20. Divisions: Brewers NL Central 9/15, Dodgers NL West 9/17, Braves NL East 9/20. **Corrected the snapshot that listed the Rays as AL East champions (IR-32).** | Seeds, matchups, or first-pitch times. URL redirects to a related article while retaining the tracker text (redirect irregularity stands). |
| MLB postseason round calendar (multiple reports incl. [NBC](https://www.nbc.com/nbc-insider/when-do-the-2026-mlb-playoffs-start) and MLB's tracker) | Wild Card Series Sep 29-Oct 1 (all four, best-of-3), Division Series Oct 3-10, LCS Oct 11-20 (NLCS G1 Oct 11, ALCS G1 Oct 12), World Series G1 Fri Oct 23 with G7 Oct 31; five no-game dates (10/2, 10/21, 10/22, 10/25, 10/29). Matches the stored date skeleton. | Any game time. Early-round times "will be released round by round" and were still unpublished on 2026-09-21. |
| [MLB Stats API seasons](https://statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029) / [2027](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2027) / [2028](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2028) / [2029](https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=2029) | Range query returns **2026 only**; individual 2027 query returns the released frame we store; 2028/2029 return empty. Resolves the headline contradiction (IR-33). | Anything about 2028/2029 beyond "not in this API." |
| Super Bowl LXIII announcement (2026-03-30, NFL Annual Meeting) — [KLAS via WJHL](https://www.wjhl.com/news/national/the-super-bowl-will-return-to-las-vegas-in-2029/), [fbschedules](https://fbschedules.com/super-bowl-lxiii-to-be-played-at-allegiant-stadium-in-las-vegas/), [Wikipedia](https://en.wikipedia.org/wiki/Super_Bowl_LXIII) | Super Bowl LXIII at Allegiant Stadium on **Sunday, February 11, 2029** — the exact day is in the announcement. Date promoted from ESTIMATED to VERIFIED (IR-34). | That the NFL cannot still adjust its calendar; fbschedules keeps "tentative" language. |
| [Valkyries local TV/radio release](https://valkyries.wnba.com/news/golden-state-valkyries-announce-local-television-and-radio-broadcast-schedule-20260425) | Full 2026 broadcast table (45 rows incl. preseason) with a **per-game radio column**: 27 rows on 95.7 The Game + Audacy; 18 rows Audacy-app only (streaming → not counted busy). Times are PT. Date discrepancy for the Sep 18/19 home games flagged (IR-35). | Playoff radio carriage (not published) or 2027+ fixtures. |
| [Valkyries September fan guide](https://valkyries.wnba.com/news/valkyries-fan-guide-september-2026) / [playoff ticket release](https://valkyries.wnba.com/news/golden-state-valkyries-announce-2026-wnba-playoffs-ticket-information-20260908) | 2026 playoffs begin Sun Sep 27; the Valkyries clinched and host their first playoff game at Chase Center; regular season ends Sep 24. | Their seed, opponent, or any tip time. |
| Warriors radio partnership ([warriorsworld](https://www.warriorsworld.net/warriors-reach-agreement-with-95-7-the-game-kgmz-fm/), [Press Democrat](https://www.pressdemocrat.com/article/sports/warriors-switching-to-95-7-the-game-for-radio-broadcasts/)) and [95.7 The Game](http://www.957thegame.com/categories/warriors) | KGMZ 95.7 is the Warriors' radio flagship since 2016 ("virtually every Warriors game including the playoffs"); the station posted the 2026-27 schedule on 2026-08-25. | Per-game carriage when a conflict moves a game; reception measurement. |
| [CBS Sports Warriors grid](https://www.cbssports.com/nba/teams/GS/golden-state-warriors/schedule/) + [preseason](https://www.cbssports.com/nba/teams/GS/golden-state-warriors/schedule/preseason/) + [ESPN API spot-check](http://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/9/schedule?dates=2026-2027) | Full 2026-27 tip-off list transcribed (times ET): 6 preseason + 80 regular rows (count flagged vs the nominal 82; up to two rows unreconciled). ESPN API opener matches. | League-source verification of every row (secondary grid; league feed wins on conflict). |
| [Sharks 2026-27 broadcast release](https://www.nhl.com/sharks/news/san-jose-sharks-announce-broadcast-schedule-for-2026-27-season), [Inside Radio](https://www.insideradio.com/free/streaming-with-the-sharks-san-jose-nhl-team-going-strong-with-streaming-only-distribution/article_88c12110-d6e5-11ee-bacd-9f5bb21101ca.html), [NBC Bay Area](https://www.nbcbayarea.com/news/sports/sharks-launch-audio-streaming-network-leave-kfox-radio-after-20-years/2445583/) | All Sharks games are app/streaming; no Bay Area AM/FM flagship since leaving KUFX in 2021. Excluded from busy time (IR-36). | Coverage on undocumented out-of-market terrestrial affiliates. |

### Re-verified 2026-09-21 (session 2, same day, later pass)

| Primary source | What was observed | What it does NOT prove |
|---|---|---|
| [49ers.com full 2026 schedule](https://www.49ers.com/schedule/) | All 3 preseason results (L 13-19, W 41-17, W 18-12) and all 16 regular-season kickoffs identical to the stored rows. **Per-game radio column transcribed for the first time:** Week 2 (09-20, FINAL W 35-13) and Week 3 (09-27) list KSFO 810 AM / KSAN 107.7 FM; Weeks 4-18 list KSAN 107.7 FM / KNBR 104.5 FM / 680 AM; the Melbourne opener (09-10) and preseason list no station. Week 18 still date/time TBD (at Arizona, State Farm Stadium). | Postseason participation; Week 18 date/time; per-game carriage at a 94122 address. |
| [Athletics schedule, week of 09-21 (statsapi.mlb.com, teamId=133)](https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-21&endDate=2026-09-27&teamId=133) | Every A's home game through 09-27 is at **Sutter Health Park, Sacramento** (venue id 2529): vs LAA 09-22/23, vs HOU 09-24/25/26 at 6:40 PM PT; 09-27 at 12:05 PM PT. Consistent with the KSTE 650 AM (Sacramento) / KNEW 960 AM (Bay Area) radio note. | Per-game KNEW/KSTE carriage; reception in 94122. |
| [MLB Stats API — 2026 postseason re-query (09-28 → 10-31)](https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31) | Fresh query returned **53 postseason game records**; every record still carries the 07:33:00Z sentinel, `startTimeTBD=true` and seed-placeholder teams. **No first-pitch time published as of 2026-09-21.** Wild Card Series begin Tuesday 2026-09-29 per the clinch tracker. | Any time; any matchup (teams are placeholders). |
| [MLB Stats API — season frames 2026 and 2027](https://statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029) | 2026 frame re-verified live (spring 02-20 → 03-24, regular 03-25 → 09-27, All-Star 07-14, postseason 09-28 → 10-31); 2027 frame re-verified live (spring 02-19 → 03-24, full Opening Day 03-25, All-Star 07-13, regular 03-25 → 09-26, postseason 09-27 → 10-31). Range query returns 2026 only; 2028/2029 remain absent (ESTIMATED). | Exact 2028/2029 dates; per-game times in 2027. |
| [MLB clinch tracker re-read](https://www.mlb.com/news/2026-postseason-teams) | Still exactly six berths (Rays 9/11, Brewers 9/11, Dodgers 9/14, Yankees 9/14, Braves 9/18, Red Sox 9/20); divisions Brewers/Dodgers/Braves as stored; tracker text: Wild Card Series "begin Tuesday, Sept. 29", two best division winners in each league get first-round byes. No new clinch since session 1. | Seeds beyond clinches, matchups, times. |

### Duration research added 2026-09-21

NBA **150** and WNBA **120** minutes are planning lengths, like the other
leagues. Secondary references: NBA 2025-26 tip-to-buzzer ≈ 2:18-2:19
([sportsgeardaily](https://sportsgeardaily.com/basketball/how-long-are-basketball-games),
[alibaba product-insights](https://www.alibaba.com/product-insights/how-long-is-the-average-basketball-game-2026-guide.html));
WNBA ≈ 1:45-2:00
([sportsmonkie](https://sportsmonkie.com/how-long-are-wnba-games/),
[gametimehero](https://www.gametimehero.com/blog/how-long-is-a-wnba-game),
[opensourcesports](https://opensourcesports.io/rules/basketball-wnba/rules-of-play-game-duration)).
Not verified current-season league averages; overtime can overrun.
