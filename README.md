# VacationSchedule — Free Time Scoreboard

**When is the best time to take a vacation in 2026–2029?** Specifically: which days,
and which hours within those days, have no live sports reachable on a standard AM/FM
radio in the Outer Sunset, San Francisco (94122)?

A scoreboard-and-calendar web app plus the reproducible pipeline behind it.

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

## The headline answer

**It depends on whether Spring Training games count as "MLB games."** Both readings are
computed and shown in the app.

### If Spring Training counts (strict)

| Year | Best window | Length | Status |
|---|---|---|---|
| 2026 | Feb 9 → Feb 19 | **11 days** | VERIFIED |
| 2027 | Feb 1 → Feb 8 | 8 days | MLB VERIFIED, NFL EST |
| 2028 | Jan 31 → Feb 7 | 8 days | ESTIMATED |
| 2029 | Jan 29 → Feb 5 | 8 days | ESTIMATED |

> **There is no fully-verified 1-, 2- or 3-week window with zero MLB and zero NFL games
> in any year, and 2026's 11-day window is already in the past.** The dependable run
> every year is Conference-Championship Sunday → Pro Bowl Games (Tuesday of Super Bowl
> week): 8–11 days, never a full two weeks.

### If only regular season + postseason count

Every year offers 5–6 weeks: **2026 (44 days) > 2029 (41) > 2028 (40) > 2027 (38)**.
That comfortably satisfies a 2- or 3-week trip.

Full derivation and provenance: [`docs/VACATION-WINDOWS.md`](docs/VACATION-WINDOWS.md).

---

## What "free" means

A minute is free when **none** of these are on air:

- MLB (Giants and A's flagged **high priority**; all 30 clubs shown)
- NFL — San Francisco 49ers, preseason **and** regular season and postseason (**high priority**)
- Stanford NCAAF, California NCAAF (**high priority**)
- San Jose Earthquakes MLS (**high priority**)
- Westwood One Sports national NFL radio broadcasts

Free time is resolved at **time-of-day granularity in Pacific Time**. Games 1–5 PM and
8–10 PM leave **5–8 PM free** rather than marking the day busy.

### Radio in the Outer Sunset

**KNBR 680 AM / 104.5 FM** is the radio home of the 49ers, Giants, Stanford, Cal, USF
men's basketball and the Earthquakes — one station covering nearly everything in scope.
It is a 50,000-watt non-directional station licensed to San Francisco. 49ers games also
air on KSAN 107.7 FM, KSFO 810 AM and KTCT 1050 AM.

> **Honest limitation:** there is **no** window in any year with zero live Bay Area
> sports radio. The Warriors and Sharks run November–June, and Stanford, Cal and USF
> basketball are on KNBR through mid-March — which lands squarely inside the February
> windows recommended above. "Free" means free of the five listed sports, not of all
> sport. See [`docs/LIMITATIONS-NEXT.md`](docs/LIMITATIONS-NEXT.md).

---

## Data honesty

This project's core rule is that **a game the site covers is never reported as free**,
and **an estimate is never presented as a schedule**.

- **2026 is verified** against league-owned sources; **2027 MLB is verified** (released
  2026-07-16, provisional pending the CBA).
- **2028–2029 (MLB) and 2027–2029 (NFL beyond verified Super Bowl sites) are ESTIMATED**
  and labelled as such everywhere. `statsapi.mlb.com/api/v1/seasons?season=2028` (and
  2029) returns an empty list — MLB's own machine-readable signal that those schedules
  are unreleased. Every estimated row carries a `basis` field and a `source` reading
  `"NOT RELEASED"` rather than a fabricated URL.
- **Games with an official date but no announced time block conservatively** rather than
  disappearing. They render at reduced opacity with a `Time TBD` chip.
- **53 items are flagged for review** and listed on the Needs Review tab.

---

## The bug this project was built to fix

An earlier version reported **2026-09-29 (MLB Wild Card Game 1) as a free day**, because
games whose start times were unannounced were dropped from the calculation. Three real
bugs were found and fixed:

| Bug | Effect | Fix |
|---|---|---|
| Un-timed games returned `None` | Wild Card day reported **free** | Block the league's TBD envelope; flag `time_confirmed = False` |
| Same-`tzinfo` datetime subtraction | Every DST day read as 24 h | Normalize to UTC before all arithmetic |
| Filtering without clipping | Overnight games double-counted | Added `clip()` |

Details in [`docs/IRREGULARITIES.md`](docs/IRREGULARITIES.md) (IR-14, IR-15, IR-16).

---

## Layout

```
site/index.html          scoreboard + calendar UI (4 tabs)
site/styles.css          dark scoreboard theme
site/app.js              browser engine + rendering
site/data/               generated bundle - do not hand-edit

scripts/lib_windows.py   the free/busy engine (stdlib only)
scripts/build_data.py    normalizes verified sources -> the bundle
scripts/analyze_vacation.py   computes vacation windows
scripts/js_harness.js    runs site/app.js under Node for parity testing

data/verified/           hand-curated, source-attributed inputs
data/analysis/           generated analysis output
tests/                   42 tests (incl. parity + DOM)
docs/                    methodology, sources, irregularities, limitations
```

## Rebuild and test

```bash
python3 scripts/build_data.py          # regenerate the bundle
python3 scripts/analyze_vacation.py    # print both interpretations
python3 -m unittest discover -s tests  # 42 tests
```

The suite includes two unusual checks worth knowing about:

- **`tests/test_parity_js.py`** runs the *real* `site/app.js` under Node and diffs it
  against the Python engine for **all 95 bundle dates** plus the DST boundaries. They agree to
  the minute. Two independent implementations of the same algorithm will drift; this
  catches it.
- **`tests/render_check.js`** loads the real `index.html` into jsdom, fires
  `DOMContentLoaded`, clicks the real navigation buttons and asserts what the user sees
  — including that 2026-09-29 is **not** free.

Optional, for the render check: `npm install --no-save jsdom`.

---

## Docs

| File | Contents |
|---|---|
| [`docs/VACATION-WINDOWS.md`](docs/VACATION-WINDOWS.md) | The answer, both interpretations, year-by-year provenance |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | The algorithm, timezone rules, durations, the TBD envelope |
| [`docs/SOURCES.md`](docs/SOURCES.md) | Every source with trust level, plus abandoned ones |
| [`docs/IRREGULARITIES.md`](docs/IRREGULARITIES.md) | 16 flagged irregularities, what was done about each |
| [`docs/LIMITATIONS-NEXT.md`](docs/LIMITATIONS-NEXT.md) | Real gaps and suggested next work |

All sources retrieved **2026-09-20**.
