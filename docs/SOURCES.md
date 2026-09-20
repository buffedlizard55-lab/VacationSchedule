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
