# VacationSchedule — Free Time Scoreboard

**When is the best time to take a vacation in 2026–2029?** Specifically: which days,
and which hours within those days, have no live sports reachable on a standard AM/FM
radio in the Outer Sunset, San Francisco (94122)?

A scoreboard-and-calendar web app plus the reproducible pipeline behind it — now with
**three comparable coverage sections**.

---

## Try it

```bash
cd site && python3 -m http.server 8080 --bind 0.0.0.0
# open http://localhost:8080
```

No build step, no dependencies. `site/index.html` loads a static data bundle and
`site/app.js`. It works **offline**; when it has network access it also fetches the
authoritative MLB schedule live from `statsapi.mlb.com` and labels which mode it is in.

---

## The three sections

Every number on the site (day board, free windows, vacation windows) is recomputed for
the section you select in the header.

| # | Busy when any of these is on air | Longest clean run, 2026–2029 |
|---|---|---|
| **1** | MLB (Giants + A's high priority, all 30 clubs) · 49ers preseason+regular+postseason (high priority) · Westwood One national NFL radio | 11 d strict / **44 d** regular |
| **2** | Section 1 **+** Stanford NCAAF, California NCAAF (high priority) | identical to Section 1 |
| **3** | Section 2 **+** San Jose Earthquakes MLS (high priority) — the original "What free means" | 11 d strict / **12 d** regular |
| *all* | Everything the project tracks (adds Westwood One national **NCAA** football, which the request does not list) | shown for completeness |

### The headline answer

**It depends on whether Spring Training counts as "an MLB game."** Both readings are
computed and shown.

**If Spring Training counts** — it is real MLB baseball and it is on KNBR — then
**no section gives you two weeks in any year**. The best you get is 8–11 days between
Conference-Championship Sunday and the Pro Bowl Games. 2026's 11-day run
(Feb 9 → Feb 19) is already in the past.

**If only the regular season and postseason count**, Sections 1 and 2 open a 5–6 week
corridor from the day after the Super Bowl to Opening Day: 2026 (44 d), 2027 (38 d),
2028 (40 d), 2029 (41 d). **Section 3 caps out at 12 days** — adding the Earthquakes is
the one change that costs you the trip, because MLS plays weekends from late February.

> **Adding Stanford and Cal costs nothing.** Sections 1 and 2 have the same longest run
> in all four years under both readings; every Stanford/Cal game date already falls
> inside the MLB season frame or the NFL season span.

Full derivation: [`docs/VACATION-WINDOWS.md`](docs/VACATION-WINDOWS.md).

---

## What "free" means

A minute is free when **none** of the games in the selected section are on air:

- MLB (Giants and A's flagged **high priority**; all 30 clubs shown)
- NFL — San Francisco 49ers, preseason **and** regular season and postseason (**high priority**)
- Stanford NCAAF, California NCAAF (**high priority**) — Section 2 and up
- San Jose Earthquakes MLS (**high priority**) — Section 3
- Westwood One Sports national NFL radio broadcasts

Free time is resolved at **time-of-day granularity in Pacific Time**. Games 1–5 PM and
8–10 PM leave **5–8 PM free** rather than marking the day busy. Games the project tracks
but the selected section does not count are **shown, never hidden** — the day board lists
them under "Tracked, but not counted in Section N".

### Radio in the Outer Sunset

**KNBR 680 AM / 104.5 FM** is the radio home of the 49ers (flagship since 2005), Giants,
Stanford, Cal, USF men's basketball and the Earthquakes — one station covering nearly
everything in scope — and is a **verified Westwood One Sports NFL affiliate for San
Francisco** along with KTCT 1050 AM and the 104.5 HD-2 subchannel. 49ers games also air
on KSAN 107.7 FM and KSFO 810 AM. Cal football's own 2026 schedule lists **KSFO 810 AM**
for every game except the Big Game (KNBR). A's games are on **KNEW 960 AM** in the Bay
Area (KSTE 650 AM is the Sacramento flagship). See the app's **Radio** tab and
[`docs/SOURCES.md`](docs/SOURCES.md).

> **Honest limitation:** there is **no** window in any year with zero live Bay Area
> sports radio. The Warriors and Sharks run November–June, and Stanford, Cal and USF
> basketball are on KNBR through mid-March — which lands squarely inside the February
> windows recommended above. "Free" means free of the sports listed in your section,
> not of all sport. See [`docs/LIMITATIONS-NEXT.md`](docs/LIMITATIONS-NEXT.md).

---

## Data honesty

This project's core rule is that **a game the site covers is never reported as free**,
and **an estimate is never presented as a schedule**.

- **2026 is verified** against league-owned sources; **2027 MLB is verified** (released
  2026-07-16, provisional pending the CBA).
- **The 2026 MLB postseason dates are verified per date** from the Stats API — including
  the five travel days (10-02, 10-21, 10-22, 10-25, 10-29) on which **no game is
  possible under any scenario** and which an earlier revision wrongly blocked.
  First-pitch **times** are still unpublished and are never invented: those days carry a
  `Time TBD` chip and a conservative envelope.
- **2028–2029 (MLB) and the NFL beyond 2026-27 are ESTIMATED** and labelled as such
  everywhere. `statsapi.mlb.com/api/v1/seasons?season=2028` returns an empty list —
  MLB's own machine-readable signal that those schedules are unreleased. Every estimated
  row carries a `basis`/`status` field and a source reading `"NOT RELEASED"` rather than
  a fabricated URL.
- **Super Bowl LXIII is now official** (Las Vegas, 2029-02-11) — this closes IR-12.
- **Games with an official date but no announced time block conservatively** rather than
  disappearing. They render at reduced opacity with a `Time TBD` chip.
- **A day inside an NFL season the bundle has no game for is blocked, not called free.**
  The project tracks the 49ers and the Westwood One national feed — not all 272 NFL
  games — so every remaining NFL game day (Sunday/Monday/Thursday, plus December
  Saturdays) carries a date-level placeholder. That is 440 records instead of 203.
- **87 items are flagged for review** and listed on the Needs Review tab.

---

## The bugs this project was built to fix

An earlier version reported **2026-09-29 (MLB Wild Card Game 1) as a free day**, because
games whose start times were unannounced were dropped from the calculation. Then the
day board reported **2027-01-17 (Wild Card Sunday)** as free whenever the 49ers were not
the listed participant, because the national radio round had no per-date record.

| Bug | Effect | Fix |
|---|---|---|
| Un-timed games returned `None` | Wild Card day reported **free** | Block the league's TBD envelope; flag `time_confirmed = False` |
| Same-`tzinfo` datetime subtraction | Every DST day read as 24 h | Normalize to UTC before all arithmetic |
| Filtering without clipping | Overnight games double-counted | Added `clip()` |
| Postseason blocked as one span | Five game-free travel days hidden | Block only the official per-date list |
| No national-radio record for playoff rounds | Wild Card Sunday read **free** | NFL round records from the league's key-dates release |
| No data at all inside an MLB season frame | Any offline day read **free** | Season-frame fallback blocks conservatively and says so |
| No NFL record for a slate date (bye week, unpublished national window) | An NFL Sunday read **free** in 2027-2029 | One date-level placeholder per NFL game day, tagged `season_frame` |

Details in [`docs/IRREGULARITIES.md`](docs/IRREGULARITIES.md).

---

## Layout

```
site/index.html          scoreboard + calendar UI (6 tabs)
site/styles.css          dark scoreboard theme
site/app.js              browser engine + rendering
site/data/               generated bundle - do not hand-edit

scripts/lib_windows.py       the free/busy engine (stdlib only)
scripts/nfl_calendar.py      the NFL calendar, one verified/estimated date at a time
scripts/build_data.py        normalizes verified sources -> the bundle
scripts/analyze_vacation.py  computes vacation windows for every section
scripts/js_harness.js        runs site/app.js under Node for parity testing

data/verified/           hand-curated, source-attributed inputs
data/analysis/           generated analysis output
tests/                   65 tests (incl. parity + DOM)
docs/                    methodology, sources, irregularities, limitations
```

## Rebuild and test

```bash
python3 scripts/build_data.py          # regenerate the bundle
python3 scripts/analyze_vacation.py    # print both interpretations, all sections
python3 -m unittest discover -s tests  # 65 tests
```

The suite includes three unusual checks worth knowing about:

- **`tests/test_parity_js.py`** runs the *real* `site/app.js` under Node and diffs it
  against the Python engine for **every bundle date, every section, and with and without
  the MLB season-frame fallback**. They agree to the minute. Two independent
  implementations of the same algorithm will drift; this catches it.
- **`tests/render_check.js`** loads the real `index.html` into jsdom, fires
  `DOMContentLoaded`, clicks the real navigation buttons **and the real section
  switcher**, and asserts what the user sees — including that 2026-09-29 is **not** free
  and that 2026-10-02 **is**.
- **`tests/test_free_time.py::TestWeekWindowInvariant`** proves the conservative season
  spans cannot hide a week: every 7-day run ends before the Hall of Fame Game.

Optional, for the render check: `npm install --no-save jsdom`.

---

## Docs

| File | Contents |
|---|---|
| [`docs/VACATION-WINDOWS.md`](docs/VACATION-WINDOWS.md) | The answer, per section, both interpretations, year-by-year provenance |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | The algorithm, sections, timezone rules, durations, the TBD envelope |
| [`docs/SOURCES.md`](docs/SOURCES.md) | Every source with trust level, plus abandoned ones |
| [`docs/IRREGULARITIES.md`](docs/IRREGULARITIES.md) | Every flagged irregularity, what was done about each |
| [`docs/LIMITATIONS-NEXT.md`](docs/LIMITATIONS-NEXT.md) | Real gaps and suggested next work |

All sources retrieved **2026-09-20**.
