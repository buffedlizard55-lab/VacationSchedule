# Sources

Every source consulted, with retrieval date, what was taken from it, and its
trust level. **All retrieved 2026-09-20.**

Trust levels:

- **PRIMARY** — league-owned or league-operated. Authoritative.
- **BROADCASTER** — the rights holder's own site. Authoritative for what it broadcasts.
- **SECONDARY** — third-party aggregator. Used only to cross-check or fill a gap,
  and always noted where it disagreed with a primary source.

---

## Primary — MLB

### MLB Stats API — season frames
`https://statsapi.mlb.com/api/v1/seasons?sportId=1&season=YYYY`

**PRIMARY.** Returns a season record for **2026 and 2027 only**:

| Field | 2026 value | 2027 value |
|---|---|---|
| `springStartDate` | 2026-02-20 | **2027-02-19** |
| `regularStartDate` | 2026-03-25 | **2027-03-25** |
| `allStarDate` | 2026-07-14 | **2027-07-13** |
| `regularSeasonEndDate` | 2026-09-27 | **2027-09-26** |
| `postSeasonEndDate` | 2026-10-31 | **2027-10-31** |

**2028 and 2029 return an empty `seasons` list.** That is MLB's own machine-readable
statement that those schedules are unreleased, and why every 2028–29 figure in this
project is labelled ESTIMATED.

**2027 change-of-record:** when this project was first built, the API returned only
2026. MLB released the 2027 schedule on **2026-07-16** (`mlb.com/press-release/
press-release-mlb-announces-2027-spring-training-schedule`): Opening Night (matchup
TBD, Netflix) Wed 2027-03-24, Opening Day Thu 2027-03-25 (14 games), All-Star Game
Tue 2027-07-13 at Wrigley Field. The 2027 API records are **VERIFIED but provisional**:
the CBA expires 2026-12-01 and a lockout could delay or cancel games (IR-19).

### MLB Stats API — schedule
`https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&gameType=R&fields=dates,date,games,gameDate,teams,away,home,team,id`

**PRIMARY.** `gameDate` is **UTC**. Practical notes:

- An 8-day range returns ~2 chunks; 15 days ~3. The app requests one day at a time.
- Postseason requires `gameType=R,E,S,D,L,F,W`.
- MLB regular season 2026 = **187 distinct dates**, 2026-03-25 → 2026-09-27 inclusive.

### MLB Stats API — 2026 postseason bracket
`https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31&gameType=E,S,D,L,F,W`

**PRIMARY, but incomplete.** Round **dates** are official; **first pitch times are
not.** See "Known data problems" below.

### MLB.com — playoff picture
`https://www.mlb.com/news/mlb-playoff-picture-and-bracket-2026`

**PRIMARY** (dated 2026-09-19). Clinched teams as of that date: Rays, Brewers
(NL Central), Dodgers (NL West, 13th division title in 14 years), Yankees, Braves.
**Matchups and times were still TBD.**

---

## Primary — NFL

### Westwood One Sports — official NFL schedule
`https://www.westwoodonesports.com/nfl-schedule/`

**BROADCASTER / PRIMARY for radio.** All four pages read. **70 entries**,
2026-09-20 → 2027-01-10. Format is `DATE away@home`.

**Critical caveat:** the times listed are **radio air time in Eastern Time, not
kickoff time.** The engine takes the earlier of air time and kickoff, so Westwood One
games block slightly longer than their nominal duration.

Also carries one NCAA row: `9/19 7:00p LSU@OleMiss`.

### Westwood One Sports — station finder
`https://www.westwoodonesports.com/station-finder`

**BROADCASTER.** Confirms the San Francisco NFL/NCAA radio affiliates are
**KNBR-AM, KNBR-FM and KTCT-AM** (this closes IR-10). The whole station table was
retrieved 2026-09-20.

### San Francisco 49ers — official schedule
`https://www.49ers.com/schedule/`

**PRIMARY.** Full 2026 preseason + regular-season schedule re-retrieved 2026-09-20.
Preseason: 08-13 vs TEN (6:00 PM PT, L 13-19), 08-20 @LAC (7:00 PM PT, W 41-17),
08-27 @LV (5:00 PM PT, W 18-12). Regular season: Week 1 @LAR in Melbourne 09-10
(5:35 PM PT, W 27-7 — the NFL's first game in Australia), Week 2 vs MIA 09-20,
Week 3 vs ARI 09-27, Week 4 vs DEN 10-04, Week 5 @SEA 10-11, Week 6 vs WAS 10-19
(MNF), Week 7 @ATL 10-25, **Week 8 BYE**, Weeks 9–17 per `bay_area_2026.json`.
Week 18 @ARI is date-TBD (league sets it late season). Radio: KSAN 107.7 FM /
KNBR 680 AM & 104.5 FM / KSFO 810 AM.

### ESPN NFL league calendar
`http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20260920`

**SECONDARY.** Used for week boundaries and preseason dates. The dedicated
`/schedule` endpoints are **dead** — see "Abandoned sources".

---

## Primary — Bay Area college and MLS

### Stanford Cardinal
- `https://gostanford.com/news/2026-08-24/2026-season-begins-with-week-0-matchup-against-hawaii-at-stanford-stadium` — Week 0 opener, **2026-08-29**.
- `https://gostanford.com/news/2026-05-27/game-times-tv-networks-announced-for-select-games` — announced kickoff times.

**PRIMARY.** Only *select* games have announced times.

### California Golden Bears
`https://calbears.com/news/2026/5/15/acc-releases-full-2026-friday-football-schedule.aspx`

**PRIMARY.** ACC Friday Football and the full 2026 schedule.

### San Jose Earthquakes
`https://www.sjearthquakes.com/news/news-earthquakes-announce-2026-major-league-soccer-schedule`

**PRIMARY.** Confirms the 2026 season opened **2026-02-21**. Only fixtures from
2026-08-01 onward were retrieved.

---

## Radio — which stations carry what in Outer Sunset 94122

### KNBR 680 AM / 104.5 FM — the decisive finding
- `https://www.cumulusmedia.com/2026-04-15/san-francisco-49ers-announce-multi-year-partnership-extension-with-cumulus-medias-knbr/`
- `https://www.49ers.com/fans/tv-radio`

**PRIMARY.** KNBR 680 AM / 104.5 FM is the radio home of the **49ers, Giants,
Stanford Cardinal, Cal Golden Bears, USF men's basketball, and San Jose Earthquakes.**
The 49ers' flagship partnership with Cumulus Media / KNBR runs **through the 2030
season**. KNBR 680 is a **50,000-watt non-directional** station licensed to San
Francisco — strong, clean coverage of the Outer Sunset on a standard AM/FM radio.

**This single station covers nearly every sport the user prioritised**, which is why
the site treats KNBR as the reference receiver.

### Other 49ers outlets
`https://www.49ers.com/fans/tv-radio`

**PRIMARY.** KSAN 107.7 FM "The Bone", KSFO 810 AM, and KTCT 1050 AM also carry
49ers games; KSFO/KTCT simulcast August–October when the Giants are playing.
Play-by-play: Greg Papa, with Tim Ryan.

---

## Secondary — cross-checks

Used to fill gaps or verify. **Where a secondary source disagreed with a primary
source, the primary source won** and the disagreement was logged in
[`IRREGULARITIES.md`](IRREGULARITIES.md).

- `https://www.playoffsschedules.com/` — postseason round dates
- `https://www.nbc.com/nbc-insider/...` — Wild Card broadcast rights (NBC/Peacock)
- `https://www.sportsbrackets.net/` — round dates
- `https://www.calfootball.com/` — **JSON-LD was the sole outlier** for Cal @ Syracuse. See IR-04.
- `https://www.seatgeek.com/` — kickoff times
- `https://en.wikipedia.org/` — Super Bowl dates and venues
- The Athletic (structured data) — schedule cross-check

---

## Duration research

| Claim | Source |
|---|---|
| MLB average game time 2026 = 2:44 | `https://sports.betmgm.com/en/blog/mlb/average-game-time-in-mlb-bm23/` |
| NFL 3:12, NCAA FBS 3:24, halftimes 12 / 20 min | `https://www.sportsgeardaily.com/football/how-long-are-football-games` |
| MLS ~2:00 | `https://tickpick.com/blog/how-long-are-mls-games/` |

**SECONDARY.** These are blog/industry figures, not league statistics, and they are
the only invented numbers in the busy-block computation.

---

## Known data problems

### MLB postseason times do not exist yet
The Stats API serves 2026 postseason games with **placeholder team names** and a
fabricated `gameDate` of `...T07:33:00Z` (12:33 AM PT). Round dates are official;
**no first pitch times exist anywhere.** This is not a retrieval failure — the times
are genuinely unannounced. The engine blocks the MLB envelope (15:00–23:59 PT) on
those dates rather than reporting them free.

### Westwood One publishes air time, not kickoff
Noted above. Handled by taking the earlier of the two.

---

## Abandoned sources

| Source | Why abandoned |
|---|---|
| nflverse `games.csv` | 276 chunks to read; impractical |
| Pro Football Reference `/years/2026/games.htm` | 13 chunks, never readable past the header |
| `site.api.espn.com/.../football/nfl/schedule` | **404** |
| `site.api.espn.com/.../football/college-football/schedule` | **404** |
| `site.web.api.espn.com/.../nfl/schedule?dates=...&limit=300` | **404** |
| `sports.core.api.espn.com/.../seasons/2026/types/2/weeks/N/competitions` | **404** |
| `247sports` | Returned garbled content |

Working ESPN alternatives: `.../scoreboard?dates=` and `.../weeks/N/events`.

---

## Unverified — flagged for review

These could **not** be confirmed and are treated as unknown, never assumed (the list
has shortened since the original build — IR-10 and IR-11 were resolved during the
2026-09-20 review):

- **The Athletics' Bay Area radio flagship.** Resolved: **KSTE 650 AM (Sacramento)**
  flagship + **KNEW 960 AM (Bay Area)**, per ESPN/MLB/A's announcements (Feb 2025).
- **KZSU 90.1 FM** (Stanford) and **KGO 810 AM** (Cal) as additional outlets — plausible
  but not confirmed for 2026.
- **2027–2029 NFL playoff round dates.** The 2026–27 cycle is verified; later cycles
  use a day-of-week template anchored to each verified Super Bowl. Marked ESTIMATED.

---

## Pro Bowl Games (NFL all-star)

- `https://www.espn.com/nfl/story/_/id/46684395/nfl-pro-bowl-festivities-moving-tuesday-super-bowl-week`

**PRIMARY.** The NFL moved the Pro Bowl Games to the **Tuesday of Super Bowl week**
beginning with the 2025-26 cycle (announced 2025-10-22). 2026: **Tue 2026-02-03**,
Moscone Center, San Francisco (verified). 2027+ follow the same Tuesday-of-Super-
Bowl-week pattern and are marked ESTIMATED until the NFL publishes them.

---

# Added 2026-09-20 (second pass)

Every URL below was opened during this pass. Nothing here is cited from memory.

## The three coverage sections

- `data/verified/profiles.json` — the sections and their `required_tags`. The `definition`
  arrays are verbatim from the request and are asserted in
  `tests/test_free_time.py::TestCoverageSections::test_section_definitions_match_the_request`,
  so the site cannot quietly redefine what it is measuring.

## MLB — 2026 postseason, resolved per date

- `https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31&gameType=E,S,D,L,F,W`
  **PRIMARY.** Read on 2026-09-20. Returns 28 games across 28 dates:
  Wild Card 09-29/09-30/10-01 (4 games each day), Division Series 10-03…10-10,
  League Championship Series 10-11…10-20, World Series 10-23, 10-24, 10-26, 10-27,
  10-28, 10-30, 10-31. **No game exists on 09-28, 10-02, 10-21, 10-22, 10-25 or 10-29**
  — those are travel days, and the previous revision wrongly blocked five of them.
  Every `gameDate` still carries the `07:33:00Z` sentinel, i.e. no first pitch is
  published yet. Stored as `data/verified/mlb_postseason_2026.json`.
- `https://www.mlb.com/news/mlb-playoff-picture-and-bracket-2026` **PRIMARY.**
  Retrieved 2026-09-20 (page dated 2026-09-20): the Rays, Brewers, Dodgers, Yankees and
  Braves have clinched a postseason berth; the Brewers clinched the NL Central on
  2026-09-15 and the Dodgers the NL West. Matchups and first-pitch times are **not** set
  until the field is final on 2026-09-27, so the site shows MLB's own placeholder
  participants ("AL Wild Card #1") and never a guessed club.
- `https://www.usatoday.com/story/sports/mlb/2026/09/18/mlb-playoff-schedule-2026-postseason-dates-world-series/91826300007/`
  and `https://www.foxsports.com/stories/mlb/2026-mlb-playoff-schedule-dates-rounds-how-watch`
  **SECONDARY cross-checks** that agree with the API on the round dates.

## NFL — full 2026 slate, calendar, rounds and the Pro Bowl

- `https://www.nfl.com/nfl-schedule-release/` **PRIMARY.** NFL's official 2026 schedule-release page.
- `https://media.nfl.com/content/dam/communications/football-communications/2026/news/05%2014%2026%20-%202026%20NFL%20Schedule%20-%20By%20Week.pdf`
  **PRIMARY.** The official by-week release retrieved 2026-09-20. It states the
  18-week, 272-game regular-season slate. Known dates and Eastern kickoffs are stored
  in `data/verified/nfl_regular_2026.csv`; Week 16/17 flexible assignments and Week 18
  date/kickoff fields remain TBD exactly as published. This source is a league slate,
  not evidence that every game airs on the San Francisco Westwood One affiliate.
- `https://www.seahawks.com/news/nfl-announces-important-dates-for-2026-2027` **PRIMARY**
  (club republication of the NFL's key-dates release, 2026-07-07): Wild Card weekend
  **2027-01-16..18**, Divisional **2027-01-23..24**, Conference Championships
  **2027-01-31**, Super Bowl LXI **2027-02-14** at SoFi Stadium. Week 18 ends
  2027-01-09/10. Also confirms the Melbourne opener (2026-09-10) and Rio (2026-09-27).
- `https://operations.nfl.com/updates/the-game/2026-pro-bowl-games-presented-by-verizon-moved-to-tuesday-of-super-bowl-lx-week-in-bay-area/`
  **PRIMARY.** The Pro Bowl Games moved to the Tuesday of Super Bowl week: 2026-02-03,
  8:00 pm ET, Moscone Center, San Francisco. Later years follow the same pattern and are
  marked ESTIMATED.
- `https://www.nfl.com/news/las-vegas-to-host-super-bowl-lxiii-in-2029` **PRIMARY** —
  Super Bowl LXIII at Allegiant Stadium, Las Vegas, **2029-02-11**, announced
  2026-03-30 at the NFL Annual Meeting. This closes IR-12 (previously ESTIMATED).
- `https://sports.yahoo.com/articles/key-dates-2026-nfl-season-162324249.html`
  **SECONDARY** corroboration of the same round dates and the 2026-11-10 trade deadline.

## Radio — what is actually on the dial

- `https://www.cumulusmedia.com/2026/04/15/san-francisco-49ers-announce-multi-year-partnership-extension-with-cumulus-medias-knbr/`
  **PRIMARY.** KNBR 104.5 FM / 680 AM is the 49ers flagship (since 2005) and is also the
  radio home of the Giants, Stanford Cardinal, Cal Golden Bears, USF men's basketball and
  the San Jose Earthquakes. 49ers programming also airs on **107.7 The Bone (KSAN-FM)**
  and **810 AM KSFO**; KNBR programming is on the KTCT 1050 subchannel. KNBR's 50,000-watt
  signal is licensed to San Francisco.
- `https://www.westwoodonesports.com/station-finder/` **PRIMARY.** Its NFL affiliate table
  lists **San Francisco, CA: KNBR-AM, KNBR-F2, KNBR-FM, KTCT-AM**. This resolves IR-10
  (the Westwood One San Francisco affiliate was previously unconfirmed). Note the page's
  own heading still reads "NFL Regular Season (2025)" — flagged as IR-23.
- `https://calbears.com/sports/football/schedule` **PRIMARY.** Cal's own 2026 schedule
  lists **Radio: KSFO 810 AM** for every game except the 129th Big Game (2026-11-21),
  which is on **KNBR 104.5 FM / 680 AM**. This corrects the earlier assumption that Cal
  football is carried on KNBR; both stations are Cumulus and both are strong in 94122, so
  no Section 2 conclusion changes. Flagged as IR-22.
- `https://www.mlb.com/athletics/schedule/watch` **PRIMARY.** A's radio affiliates:
  **650 AM KSTE** (Sacramento flagship) and **960 AM KNEW** (Bay Area). Resolves IR-11
  for the Bay Area; KSTE's reach into 94122 is unverified (21,000 W, Rancho Cordova).
- `https://www.radioworld.com/news-and-business/cumulus-media-surrenders-license-of-san-franciscos-560-am`
  **PRIMARY.** Cumulus moved the KSFO format and calls to the **50,000-watt 810 AM**
  facility (formerly KGO) and surrendered the 560 AM licence in August 2026. This is why
  Cal football's "KSFO 810 AM" is a strong 94122 signal rather than a weak local one.
- `https://en.wikipedia.org/wiki/KSAN_(FM)` **SECONDARY.** KSAN 107.7: Class B, 8,900 W
  ERP, 354 m HAAT, licensed to San Mateo — consistent with Bay-Area-wide coverage.
- `https://publicfiles.fcc.gov/am-profile/knbr` **PRIMARY (regulator).** KNBR facility ID
  35208, licensed to San Francisco, licence expires 2029-12-01.

## Duration research

- `https://www.sportsbusinessjournal.com/Articles/2026/07/14/mlb-game-duration-up-for-the-second-straight-year/`
  **PRIMARY-adjacent.** Average nine-inning MLB game through 2026-07-08: **≈2:42**.
- `https://www.profootballnetwork.com/how-long-is-a-football-game-breaking-down-the-time-between-the-first-and-last-whistle/`
  **SECONDARY.** NFL 3:12 (12-minute halftime); NCAA 3:24 (20-minute halftime).
- `https://www.academicjobs.com/en-us/higher-education-news/how-long-is-a-college-football-game-average-326-explained-or-academicjobs-12610`
  **SECONDARY.** 2025 FBS average **3:26**.

## Abandoned in this pass

- The Westwood One station finder renders its affiliate tables as a single page with no
  per-zip filtering in the fetched HTML; the San Francisco rows were read from the flat
  NFL table instead of a 94122-specific query. The table is market-level, which is the
  right granularity for this question anyway.
