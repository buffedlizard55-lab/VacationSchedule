# Irregularities flagged for review

Every place where a source was wrong, inconsistent, ambiguous, or silent. Nothing
here was silently resolved — each item states what was found, what was done about
it, and what remains uncertain.

---

## IR-01 — 49ers coverage gaps (HIGH)

**Found:** the `49ers.com` retrieval captured most of the 2026 season but is missing
**Weeks 1, 2 and 8, and every preseason game.** Week 18 is listed as `TBD`.

**Impact:** those dates would read as **free** when 49ers games actually occur. This is
exactly the class of bug the user reported on a previous site.

**Done:** each gap is emitted into the `unresolved` array with its reason, and the UI
shows all unresolved items on the **Needs Review** tab. **The gaps are labelled, not
papered over** — but the affected days are *not* conservatively blocked, because no
date is known to block.

**RESOLVED 2026-09-20:** see **IR-17**. The "missing" weeks were re-retrieved live;
Week 8 is a BYE, Week 1 was the Melbourne game (2026-09-10), Week 2 (09-20) and
Week 6 (10-19) are now included, and the preseason is three verified games.

---

## IR-02 — MLB postseason times are fabricated, not merely absent (HIGH)

**Found:** `statsapi.mlb.com` serves 2026 postseason games with **placeholder team
names** and `gameDate = ...T07:33:00Z`, i.e. **12:33 AM Pacific**. No real first pitch
happens at that hour.

**Why it matters:** a naive parser reads `07:33:00Z` as a legitimate kickoff and
reports the whole afternoon and evening as free.

**Done:** `MLB_TBD_SENTINEL_UTC` + `is_tbd_utc()` detect the sentinel. Affected games
are routed to the conservative MLB envelope (**15:00–23:59 PT**) and flagged
`time_confirmed = False`. The sentinel instant never surfaces as a time. Test:
`test_tbd_mlb_game_blocks_conservatively`.

**Still open:** the real times. They do not exist anywhere yet.

---

## IR-03 — `postSeasonStartDate` disagrees with the first actual game (LOW)

**Found:** the Stats API reports MLB `postSeasonStartDate = 2026-09-28`, but the first
scheduled postseason games are **2026-09-29** (Wild Card Game 1). 2026-09-28 is a
travel/off day.

**Done:** both dates are blocked. The season frame keeps the API's 09-28 with a note;
the game list carries the 09-29 fixtures. No vacation window is affected.

---

## IR-04 — Cal @ Syracuse kickoff: one source disagreed (MEDIUM)

**Found:** `calfootball.com`'s JSON-LD gave **09:30 PT** for Cal @ Syracuse. Every other
source, including `calbears.com`, gave **12:30 PT**.

**Assessment:** 09:30 PT is a 12:30 PM ET kickoff. No ACC game kicks off at 12:30 ET
on a Saturday. Almost certainly a **PT/ET labelling error** in the JSON-LD.

**Done:** corrected to **12:30 PT** in `data/verified/bay_area_2026.json`, following
the primary source. Logged here because it is a genuine source conflict.

**General rule adopted:** where a secondary source conflicts with a league-owned
source, the league-owned source wins.

---

## IR-05 — 11 of 24 Stanford/Cal games have no announced kickoff (MEDIUM)

**Found:** Stanford announced times for only "select" games. Across both programmes,
**11 of 24** fixtures have a verified date but no time.

**Done:** those dates are envelope-blocked **11:00–23:59 PT** rather than guessed.
They render at reduced opacity with a `Time TBD` chip.

**Trade-off stated plainly:** this makes some genuinely free afternoons look busy.
That is deliberate — the user's stated priority is never recommending a vacation on a
day that has a game.

---

## IR-06 — Earthquakes Matchday 33 kickoff is "Time TBD" (LOW)

**Found:** the club's own release lists the **2026-10-31** match vs Real Salt Lake
with `Time TBD`.

**Done:** MLS envelope **16:00–23:59 PT** applied. Note that on this date the NCAAF
envelope (11:00–23:59) already subsumes it, so the merged block is 11:00–23:59 =
**779 minutes**, entirely unconfirmed.

---

## IR-07 — Earthquakes February–July fixtures were never retrieved (MEDIUM)

**Found:** only matches from **2026-08-01** onward are in the snapshot. The club
release confirms the season opened **2026-02-21**, so roughly five months of MLS
fixtures are absent.

**Impact:** MLS-heavy spring dates may read as free.

**Mitigating:** those dates are already blocked by MLB Spring Training, so no
vacation window in this analysis is affected. Still a real coverage hole.

---

## IR-08 — Westwood One publishes air time, not kickoff (MEDIUM)

**Found:** the schedule page lists **Eastern Time radio air times**, which precede
kickoff because of the pre-game show.

**Done:** the engine blocks from `min(air_time, kickoff)`. Westwood One games
therefore block slightly longer than their nominal duration.

**Also noted:** Denver's stadium is written two different ways on the same page —
"Empower Field at Mile High" and "Mile High Stadium". Cosmetic; no action.

---

## IR-09 — 8 Westwood One slots have no teams announced (LOW)

**Found:** slots such as the **2026-12-26** Saturday doubleheader list no teams.

**Done:** the date is still blocked (Westwood One is broadcasting), and the entry is
flagged unresolved. Blocking on an unknown opponent is the correct behaviour here.

---

## IR-10 — Westwood One's San Francisco affiliate is unconfirmed (MEDIUM)

**Found:** the Station Finder does not clearly confirm which Bay Area station carries
the national feed. **KNBR is presumed but not verified.**

**Impact:** if the affiliate were a weaker or differently-located station, Outer Sunset
reception could differ.

**Not resolved.** Flagged for manual review.

---

## IR-11 — The Athletics' Bay Area radio flagship is unidentified (LOW)

**Found:** no source consulted confirmed the A's flagship station for 2026.

**Impact:** A's games are flagged high priority per the user's instruction, but a
listener may not be able to receive them on KNBR.

**Not resolved.**

---

## IR-12 — Super Bowl LXIII has no confirmed date (MEDIUM)

**Found:** the NFL has awarded **Super Bowl LXIII to Allegiant Stadium, Las Vegas**
for the 2028 season, but has **not announced the date.**

**Done:** estimated as the **second Sunday of February 2029 = 2029-02-11**, and marked
`ESTIMATED`.

**Sensitivity:** this single date sets the best 2029 vacation window. If the Super Bowl
moves to the first Sunday (Feb 4), the window grows to **14 days**. If it moves to
Feb 18, the window **disappears**. 2029 is the least reliable year in the analysis
for this reason.

**Correction of record:** an earlier assumption placed Super Bowl LXIII at Levi's
Stadium. It is **Allegiant Stadium, Las Vegas.**

---

## IR-13 — 2027–2029 MLB and NFL seasons are unreleased (HIGH, by design)

**Found:** `statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029`
originally returned **2026 only.**

**UPDATE 2026-09-20 (see IR-19):** MLB released the 2027 schedule on 2026-07-16, so
2027 MLB is now **VERIFIED** (provisional pending the CBA). 2028 and 2029 still return
nothing from the API and remain ESTIMATED.

**Done:** those years are computed from the 2026/2027 verified frames plus each
league's published scheduling rules, and every estimated row carries `status:
ESTIMATED` with a `basis` field and a `source` field reading **"NOT RELEASED"** rather
than a fabricated URL.

This is the user's explicit requirement: estimates must be clearly marked as
estimates, not presented as real schedules.

---

## IR-14 — A same-`tzinfo` subtraction bug made every DST day 24 hours (HIGH, fixed)

**Found:** Python's `datetime` arithmetic ignores `utcoffset()` when two aware
datetimes share the *same* `tzinfo` object. So
`aware_end - aware_start` returned **24 hours for a 25-hour day.**

Proof run in-sandbox:

```
n - d                                 -> timedelta(days=1)                # 24h  WRONG
n.astimezone(UTC) - d.astimezone(UTC) -> timedelta(days=1, seconds=3600)   # 25h  RIGHT
```

A control using fixed-offset `timezone(timedelta(hours=-7))` vs `-8` correctly gave
25 h, confirming the cause was the shared `ZoneInfo`, not tzdata.

**Impact:** 2026-11-01 (a Sunday with a full NFL slate) was computed as 1440 minutes
instead of **1500**. Reported free time on DST transition days was wrong.

**Fixed:** `Interval.__init__` normalizes to UTC on construction; `span_minutes()`
re-normalizes defensively; `local_day_bounds()` and `local_wall_clock()` convert
before arithmetic. Regression tests: `test_span_minutes_is_dst_safe`,
`test_day_report_uses_true_dst_day_length`, `test_dst_days_match`.

**Rule adopted:** always `.astimezone(timezone.utc)` before subtracting or comparing
aware datetimes.

---

## IR-15 — Filtering is not clipping (HIGH, fixed)

**Found:** `intervals_for_day` selected intervals overlapping a day but left them at
full length. An overnight game was counted at **full duration on both dates.**

**Proof:** a test with an overnight fixture reported `busy_minutes = 164.0` where only
**44.0** minutes belong to the reported date.

**Fixed:** added `clip(iv, day_start, day_end)`, used by both `intervals_for_day` and
`free_windows`. Test: `test_overnight_game_blocks_two_dates`.

---

## IR-16 — Un-timed games were skipped entirely (HIGH, fixed)

**Found:** `game_to_interval` returned `None` for a game with a verified date but no
time. The day then looked empty and was reported **free**.

**Concrete failure:** **2026-09-29** (MLB Wild Card Game 1) was reported as a free
day — precisely the bug the user reported.

**Fixed:** un-timed games now block their league's TBD envelope and are flagged
`time_confirmed = False`. `day_report` gained `has_unconfirmed_times`,
`unconfirmed_minutes`, and `is_free_day = not merged`. Tests:
`test_tbd_mlb_game_blocks_conservatively`, `test_postseason_dates_are_never_free`,
`test_no_game_day_is_reported_free` (asserts **no** date carrying a game reads free,
across all 155 bundle rows).

---

## Items added in the 2026-09-20 review pass

### IR-17 — 49ers "missing weeks" were a mix of BYE, already-played, and future games (HIGH, resolved)

**Found:** IR-01 listed Weeks 1, 2, 6, 8 and all preseason as unretrieved.

**Resolution (re-retrieved live 2026-09-20):**
- Preseason is three games, now included: 08-13 vs TEN, 08-20 @LAC, 08-27 @LV.
- Week 1 = **@Rams in Melbourne 2026-09-10** (5:35 PM PT, the NFL's first game in
  Australia; final W 27-7).
- Week 2 = vs Dolphins 2026-09-20; Week 6 = vs Commanders 2026-10-19 (MNF).
- **Week 8 is a BYE week, not a missing game.** The original tool was wrong to flag it.
- Week 18 @Cardinals remains date-TBD by the league (Jan 9 or 10, 2027).

**Still open:** Week 18's exact date/time.

### IR-18 — The NFL 2026 season opener date was wrong in the snapshot (HIGH, fixed)

**Found:** `seasons.json` had `regular_season_week1_start = 2026-09-06`, but the 2026
season actually opened **Wed 2026-09-09** (Seahawks vs Patriots, NFL Kickoff), with the
Melbourne game 2026-09-10. The whole Week 1 boundary (and downstream round dates) were
a week early.

**Fixed:** Week boundaries now start 2026-09-09 and follow the NFL's official key-dates
release (seahawks.com 2026-07-07): Week 1 opens 09-09; playoffs: Wild Card 2027-01-16..18,
Divisional 01-23..24, Championships 01-31, Super Bowl LXI 02-14.

### IR-19 — The 2027 MLB season is RELEASED now (MEDIUM, blocks a change-of-record)

**Found:** the original build said the Stats API returned 2026 only. As of 2026-09-20 the
API returns a **2027** season record too (spring 2027-02-19, Opening Day 2027-03-25,
All-Star 2027-07-13 at Wrigley, regular season ends 2027-09-26). MLB released the schedule
on 2026-07-16.

**Done:** 2027 MLB is now marked **VERIFIED** (but provisional — see below).

**Still open / flag:** the current CBA expires 2026-12-01. MLB's own release notes the
calendar is contingent on a new agreement; a lockout could delay or cancel games. The 2027
MLB frame must be re-checked after a new CBA is signed before relying on it for a vacation.

### IR-20 — The vacation model over-blocked the NFL offseason (MEDIUM, fixed)

**Found:** the analyzer treated "Jan 1 → Super Bowl" as one continuous NFL block, which
implicitly marked every January day busy. But the NFL's January/February calendar is sparse
(Week 17/18, then 4 single-weekend playoff rounds, Pro Bowl Games, Super Bowl). This
**hid real clean windows** (e.g. Conference-Championship-Sunday → Pro-Bowl week = 8–11
days), which the user asked for.

**Fixed:** the analyzer now blocks the *actual* NFL dates (round dates via a day-of-week
template anchored to each cycle's Super Bowl, using the verified 2026-27 layout) instead of
a continuous span. This surfaced 8-day windows in 2027/2028/2029 under the strict reading —
still short of a full two weeks, but real and previously invisible.

### IR-21 — Pro Bowl Games (NFL all-star) now inside the window (HIGH, fixed)

**Found:** the user listed "NFL all-star games" as busy, but the model did not block the
Pro Bowl Games. The NFL moved them to the **Tuesday of Super Bowl week** (announced
2025-10-22); 2026 = Tue 2026-02-03 (Moscone Center, SF), 2027+ follow the same pattern.
Without this block the 2027+ windows were over-optimistic by one day.

**Fixed:** the Pro Bowl Games date is blocked per year (2026 VERIFIED, later years
ESTIMATED-pattern).

**Still open:** exact 2027+ Pro Bowl dates/venues are not yet published by the NFL.

---

## Items added in the 2026-09-20 second pass

### IR-12 (UPDATED) — Super Bowl LXIII's date is now official (RESOLVED)

Was MEDIUM / open: "Super Bowl LXIII has no confirmed date". The NFL announced on
2026-03-30, at the Annual Meeting, that Super Bowl LXIII will be played at Allegiant
Stadium, Las Vegas, on **2029-02-11**. The date the project had been carrying as an
estimate was correct, and is now VERIFIED with a source. `scripts/nfl_calendar.py` and
`data/verified/seasons.json` were updated; a test asserts the status is VERIFIED.

### IR-22 — California football's radio home is KSFO 810 AM, not KNBR (MEDIUM, resolved)

The Cumulus 49ers release (2026-04-15) describes KNBR as the radio home of "Stanford
Cardinal, Cal Golden Bears, USF men's basketball and San Jose Earthquakes", and the
earlier revision of this project therefore labelled every Stanford **and** Cal game as
KNBR. Cal's own 2026 schedule page disagrees: it lists **Radio: KSFO 810 AM** for every
game except the 129th Big Game (2026-11-21), which is on **KNBR 104.5 FM / 680 AM**.

**Resolution:** the team's own schedule page wins for game broadcasts; the Cumulus
release stands as a marketing description. Both are Cumulus stations in the same Daly
City building, both are strong in 94122, and neither changes any Section 2 conclusion —
the games still block. The site now says which station carries which, on the Radio tab.

### IR-23 — Westwood One's affiliate table is still labelled 2025 (LOW)

The station finder's NFL table is headed "NFL Regular Season (2025)". The San Francisco
rows (KNBR-AM, KNBR-F2, KNBR-FM, KTCT-AM) are what resolve IR-10, but they may not be
current for 2026. **Action:** re-check at the start of each season; the affiliate line is
now a single constant in `data/verified/radio_stations.json`, so it is a one-line update.

### IR-24 — 2026 postseason first-pitch times still do not exist (HIGH, self-resolving)

Unchanged in substance from IR-02 (this is the same issue, re-verified): every 2026
postseason game is served with the `07:33:00Z` sentinel. What *did* get resolved is the
**date** list — read game-by-game from the Stats API rather than assumed as a span — and
the correction that **no game can be played on 2026-10-02, 10-21, 10-22, 10-25 or
10-29**. Those five days are now correctly free of MLB where they were previously
blocked. **Action:** re-fetch daily from 2026-09-27, when MLB sets the times.

### IR-25 — The MLB season-frame fallback blocks the All-Star break (LOW, accepted)

The frame for each year spans Spring Training start → postseason end, so 2026-07-15 to
2026-07-18 (the All-Star break, when no games are played) is marked busy. Accepted
deliberately: the fallback's job is to fail safe, the break is mid-July, and it sits
outside the August–February window the request is about. A future revision could add
`complete_ranges` for the break; the 2026 postseason already has them.

### IR-26 — Sections 1 and 2 have identical results (INFORMATIONAL, not a bug)

Every Stanford and Cal game date already falls inside the MLB season frame or the NFL
season span, so the two sections produce the same longest run in all four years under
both readings. This is reported on the Compare tab rather than hidden, because it is the
answer to "does adding college football cost me anything?" — it does not. The only days
college football adds are the early-January bowl window, which is conditional on
qualifying and never creates or destroys a 7-day window.

### IR-27 — Adding the Earthquakes *does* cost the whole trip (INFORMATIONAL)

Sections 1 and 2 give a 38–44 day corridor in the regular-season reading; Section 3 gives
12 days. MLS plays weekends from late February and every 7-day window contains a weekend.
The Compare tab states this explicitly, because it is the one place where the choice of
section changes the recommendation.

### IR-28 — A's and KSTE reception in 94122 is not documented (MEDIUM, open)

KSTE 650 (Rancho Cordova, 21,000 W) is the A's flagship but is roughly 90 miles from the
Outer Sunset and its coverage of San Francisco is undocumented in any source found.
**Action for the next session:** verify with an SDR or FCC field-strength map, or treat
the A's as reachable only via KNEW 960 AM. Flagged `NEEDS_MANUAL_CHECK` in
`data/verified/radio_stations.json`; the A's are still counted as busy either way, so no
conclusion depends on it.

### IR-29 — The day board could read "free" on an NFL date without a radio record (RESOLVED 2026-09-20)

Sections 1–3 still count only the 49ers and Westwood One, not all 272 league games. The
failure mode was that a date with no published national selection had no day-board
record at all. The official full slate is now bundled and `from_nfl_schedule_radio_backstop`
adds one conservative, unresolved date-level radio envelope when needed. The day board
also displays the actual league matchups separately, so a date is never represented by
a generic season-frame phrase. The radio envelope remains visibly provisional: it does
not claim that every scheduled NFL game is on the Bay Area affiliate.

The 2027–2029 schedules are not released, so estimated season-frame records remain
necessary for those years and are still labelled ESTIMATED.


### IR-30 — 2026 NFL full slate was missing from the day board (RESOLVED 2026-09-20)

The earlier bundle had only 49ers and Westwood One records plus generic season-frame
rows. That made a user asking about a date see a shape-only NFL placeholder rather than
the actual league matchups. The official NFL by-week PDF now supplies all 272 regular-
season games in `data/verified/nfl_regular_2026.csv` and `nfl_schedule_2026` in the
browser bundle. The day board renders those rows in a separate reference panel.

This does **not** turn all 272 games into local radio occupancy. Westwood One remains the
radio source of truth. Dates with a full slate but no published Westwood One selection
get one conservative, visibly unresolved radio envelope; no matchup is invented for
that radio record. Week 16/17 flexible assignments and Week 18 date/kickoff fields are
preserved as TBD.

### IR-31 — Warriors/Sharks scope decision (RESOLVED 2026-09-20)

Warriors games on KGMZ 95.7 and Sharks broadcasts can overlap the recommended winter
windows, but they are not part of the three definitions requested. This release keeps
them outside Sections 1–3 so the comparison remains exactly MLB/49ers/Westwood One,
then Stanford/Cal, then Earthquakes. They remain prominently documented as an
out-of-scope limitation; a future opt-in section must source both official schedules
and Bay Area radio carriage before changing any score.
