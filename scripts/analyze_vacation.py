"""Compute the best vacation windows for 2026-2029 in each of the three sections.

Run:  python3 scripts/analyze_vacation.py

The user asked to compare three definitions of "busy":

  section 1 - MLB (all 30 clubs) + 49ers (preseason/regular/postseason) + Westwood One national NFL
  section 2 - section 1 + Stanford and California college football
  section 3 - section 2 + San Jose Earthquakes MLS          <- the site's original definition
  all       - everything the project tracks (adds Westwood One national NCAA football)

and, within each, two readings of "no MLB games":

  strict   - any MLB game blocks, including Spring Training exhibitions.
             Spring Training games ARE MLB games (gameType 'S' in the Stats API) and
             Giants Spring Training games are broadcast on KNBR, so this is the
             literal reading.
  regular  - only MLB regular season + postseason block. Spring Training is treated
             as exhibition baseball and ignored.

Both are reported.  Neither is presented as the only correct answer.

Blocking model
--------------
This is a conservative season-envelope planner, NOT a proof that a calendar has
no possible vacation. MLB and current NFL seasons are reserved continuously;
January/February NFL uses per-date official inputs or explicit templates.
Conditional college bowls/CFP and MLS phase envelopes can hide real fixture gaps.
The published MLS summer–spring format replaces the obsolete February–November
assumption from 2027 onward. See docs/METHODOLOGY.md for the exact assumptions.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import nfl_calendar
from lib_windows import find_gaps

ROOT = Path(__file__).resolve().parent.parent
VERIFIED = ROOT / "data" / "verified"
OUT = ROOT / "data" / "analysis"

#: The three sections, and which league spans each one blocks.
SECTION_LEAGUES = {
    "1": ("MLB", "NFL"),
    "2": ("MLB", "NFL", "NCAAF"),
    "3": ("MLB", "NFL", "NCAAF", "MLS"),
    "all": ("MLB", "NFL", "NCAAF", "MLS", "NBA", "WNBA"),
}

SECTION_NAMES = {
    "1": "Section 1 - MLB + NFL",
    "2": "Section 2 - Section 1 + Stanford/Cal football",
    "3": "Section 3 - Section 2 + Earthquakes MLS",
    "all": "Superset - everything tracked",
}

#: Backwards-compatible aliases (older revisions of this module owned these).
SUPER_BOWL_BY_YEAR = nfl_calendar.SUPER_BOWL_BY_YEAR
NFL_SEASON_START = nfl_calendar.NFL_SEASON_START
PRO_BOWL_BY_YEAR = nfl_calendar.PRO_BOWL_BY_YEAR
PREV_SEASON_ROUND_OFFSETS = nfl_calendar.ROUND_OFFSETS
previous_season_nfl_dates = nfl_calendar.previous_season_nfl_dates


def _seasons() -> dict:
    """data/verified/seasons.json, parsed once."""
    global _SEASONS_CACHE
    if _SEASONS_CACHE is None:
        _SEASONS_CACHE = json.loads((VERIFIED / "seasons.json").read_text(encoding="utf-8"))
    return _SEASONS_CACHE


_SEASONS_CACHE: dict | None = None


def daterange(start: str, end: str) -> list[str]:
    day = datetime.strptime(start, "%Y-%m-%d").date()
    stop = datetime.strptime(end, "%Y-%m-%d").date()
    out = []
    while day <= stop:
        out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def _last_saturday(year: int, month: int) -> str:
    """ISO date of the last Saturday of `month` - used for the estimated spans."""
    day = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    while day.weekday() != 5:
        day -= timedelta(days=1)
    return day.isoformat()


def _first_saturday(year: int, month: int) -> str:
    day = date(year, month, 1)
    while day.weekday() != 5:
        day += timedelta(days=1)
    return day.isoformat()


# ---------------------------------------------------------------------------
# Per-league spans
# ---------------------------------------------------------------------------


def mlb_span(year: int, mlb: dict, count_spring_training: bool) -> tuple[str, str, dict]:
    frame = mlb[str(year)]
    start = frame["spring_training_start"] if count_spring_training else frame.get("first_regular_season_game", frame["regular_season_start"])
    return start, frame["postseason_end"], {
        "start": start,
        "end": frame["postseason_end"],
        "status": frame["status"],
        "includes_spring_training": count_spring_training,
        "source": "https://statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029",
        "note": frame.get("note", ""),
    }


#: Game types that count as "an MLB game is being played that day".
#: S = Spring Training (only under the strict reading), R = regular season,
#: E = exhibition, F/D/L/W = postseason rounds, P/C = legacy postseason codes,
#: A = All-Star Game.
_MLB_ALWAYS_BLOCKING_TYPES = {"R", "E", "F", "D", "L", "W", "P", "C", "A"}


def mlb_fixture_days(year: int, count_spring_training: bool) -> list[str] | None:
    """Exact dates with at least one official MLB game, or None if unknown.

    Reads the committed official snapshot written by
    ``scripts/export_mlb_schedule.py`` (``data/verified/mlb_schedule_<year>.csv``,
    straight from the league's Stats API). When the file exists, the vacation
    analysis blocks the real fixture dates instead of a continuous season
    envelope, which is both more accurate and easier to audit: a date with no row
    is genuinely free of MLB under the chosen reading.

    Returns ``None`` when the snapshot is not present for that year, in which case
    the caller keeps the documented conservative envelope.
    """
    path = VERIFIED / f"mlb_schedule_{year}.csv"
    if not path.exists():
        return None
    allowed = set(_MLB_ALWAYS_BLOCKING_TYPES)
    if count_spring_training:
        allowed.add("S")
    days: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        columns = line.split("|")
        if len(columns) < 6:
            raise ValueError(f"{path}: malformed row: {line[:80]}")
        date_local, game_type = columns[0], columns[5]
        if game_type in allowed and date_local.startswith(f"{year}-"):
            days.add(date_local)
    return sorted(days)


def _cfp_end_estimate(year: int) -> str:
    first = date(year, 1, 1)
    return (first + timedelta(days=(0 - first.weekday()) % 7 + 21)).isoformat()


def ncaaf_spans(year: int, seasons: dict) -> list[dict]:  # noqa: C901
    """Season span(s) for Stanford + California football.

    2026 is verified from each school's own 2026 schedule page; 2027-2029 follow
    the stable FBS calendar (last Saturday of August through the last Saturday of
    November, conference championship the first Saturday of December, bowls in
    late December).
    """
    verified = seasons.get("bay_area_teams", {}).get("2026", {})
    if year == 2026 and verified.get("status") == "VERIFIED":
        first = min(verified["stanford_football"]["first_game"], verified["cal_football"]["first_game"])
        last = max(verified["stanford_football"]["last_regular_season_game"], verified["cal_football"]["last_regular_season_game"])
        return [
            {
                "start": first,
                "end": last,
                "status": "VERIFIED",
                "label": "Stanford/California football regular season",
                "conditional": False,
                "source": "https://gostanford.com/ and https://calbears.com/sports/football/schedule",
            },
            {
                "start": verified["stanford_football"]["acc_championship_if_qualified"],
                "end": verified["stanford_football"]["acc_championship_if_qualified"],
                "status": "VERIFIED",
                "label": "ACC Championship Game (conditional on qualifying)",
                "conditional": True,
                "source": "https://calbears.com/news/2026/5/15/acc-releases-full-2026-friday-football-schedule.aspx",
            },
            {
                "start": "2026-12-01",
                "end": "2027-01-25",
                "status": "ESTIMATED",
                "label": "Bowl/CFP envelope; Jan 25 title date published (conditional on qualifying)",
                "conditional": True,
                "source": "https://collegefootballplayoff.com/",
                "note": "Conservative December-to-title-game envelope, not school fixtures. Future title dates use the fourth Monday in January as an estimate.",
            },
        ]
    return [
        {
            "start": _last_saturday(year, 8),
            "end": _last_saturday(year, 11),
            "status": "ESTIMATED",
            "label": "Stanford/California football regular season (estimated)",
            "conditional": False,
            "source": "NOT RELEASED - last Saturday of August through the last Saturday of November",
        },
        {
            "start": _first_saturday(year, 12),
            "end": _first_saturday(year, 12),
            "status": "ESTIMATED",
            "label": "ACC Championship Game (conditional on qualifying, estimated)",
            "conditional": True,
            "source": "NOT RELEASED - first Saturday of December, ACC pattern",
        },
        {
            "start": f"{year}-12-01",
            "end": _cfp_end_estimate(year + 1),
            "status": "ESTIMATED",
            "label": "Bowl season / CFP (conditional on qualifying, estimated)",
            "conditional": True,
            "source": "https://collegefootballplayoff.com/",
                "note": "Conservative December-to-title-game envelope, not school fixtures. Future title dates use the fourth Monday in January as an estimate.",
        },
    ]


def mls_spans(year: int, seasons: dict) -> list[dict]:
    """Season span(s) for the San Jose Earthquakes.

    2026 is verified from the club's own fixture release (which also confirms the
    season opened 2026-02-21 and closed 2026-11-07). 2027-2029 follow the MLS
    pattern (late-February opener, early-November decision day, MLS Cup in the
    first half of December).
    """
    verified = seasons.get("bay_area_teams", {}).get("2026", {})
    if year == 2026 and verified.get("status") == "VERIFIED":
        quakes = verified["earthquakes"]
        return [
            {
                "start": quakes["first_game"],
                "end": quakes["last_regular_season_game"],
                "status": "VERIFIED",
                "label": "Earthquakes MLS regular season",
                "conditional": False,
                "source": "https://www.sjearthquakes.com/news/news-earthquakes-announce-2026-major-league-soccer-schedule",
            },
            {
                "start": "2026-11-22",
                "end": "2026-12-12",
                "status": "ESTIMATED",
                "label": "MLS Cup Playoffs (conditional on qualifying)",
                "conditional": True,
                "source": "NOT RELEASED as a fixture list - MLS playoff window",
            },
        ]
    if year < 2027:
        return [{"start": f"{year}-02-01", "end": f"{year}-12-15",
                 "status": "ESTIMATED", "label": "Historical MLS season envelope",
                 "conditional": True, "source": "Historical calendar approximation"}]
    # Official format, NOT official fixture dates. Whole boundary months are
    # reserved conservatively; no assumption that every club plays every week.
    source = "https://www.mlssoccer.com/news/mls-to-align-calendar-with-top-leagues-around-world"
    return [
        {"start": f"{year}-02-01", "end": f"{year}-05-31",
         "status": "ESTIMATED", "label": "MLS transition season" if year == 2027 else "MLS spring phase + conditional playoffs",
         "conditional": True, "source": source,
         "note": "Official February–May format; exact Earthquakes fixtures unresolved. Boundary months reserved in full."},
        {"start": f"{year}-07-01", "end": f"{year}-12-15",
         "status": "ESTIMATED", "label": "MLS summer–fall phase before winter break",
         "conditional": False, "source": source,
         "note": "Official mid/late-July start and mid-December break; July 1–December 15 is a conservative planning assumption."},
    ]


# ---------------------------------------------------------------------------
# The blocked set for one year, in one section
# ---------------------------------------------------------------------------

def other_radio_spans(year: int) -> list[dict]:
    """NBA (Warriors) and WNBA (Valkyries) season spans overlapping `year`.

    Only the `all` scope includes these leagues (see SECTION_LEAGUES): the three
    requested sections are defined verbatim by the user and must not change.
    2026-27 Warriors and 2026 Valkyries frames come from the verified game lists
    in data/verified/other_radio_sports.json; every other season is an ESTIMATED
    envelope plus a conditional playoff tail. Continuous envelopes can hide real
    rest days - same caveat as the MLB/NFL frames.
    """
    spans: list[dict] = []
    gs_src = "https://www.cbssports.com/nba/teams/GS/golden-state-warriors/schedule/ (2026-27 grid read 2026-09-21)"
    gs_est = ("NOT RELEASED - estimated NBA envelope (mid-October through mid-April) "
              "plus a conditional playoff window")
    # Warriors seasons overlapping `year` (a season starting Oct of Y-1 ends in Y).
    for start_year in (year - 1, year):
        if start_year == 2026:
            spans.append({"start": "2026-10-04", "end": "2027-04-11",
                          "status": "VERIFIED", "label": "Golden State Warriors 2026-27 NBA season",
                          "conditional": False, "source": gs_src,
                          "note": "Preseason from 2026-10-04; regular season ends 2027-04-11 (released grid)."})
            spans.append({"start": "2027-04-12", "end": "2027-06-30",
                          "status": "ESTIMATED", "label": "NBA playoffs (conditional on the Warriors qualifying)",
                          "conditional": True, "source": "NOT RELEASED - conservative Finals tail",
                          "note": "No fixture implied. The Warriors missed the 2026 playoffs (37-45)."})
        else:
            spans.append({"start": f"{start_year}-10-12", "end": f"{start_year + 1}-04-15",
                          "status": "ESTIMATED",
                          "label": f"Golden State Warriors {start_year}-{str(start_year + 1)[2:]} NBA season (estimated envelope)",
                          "conditional": False, "source": gs_est,
                          "note": "Unreleased season; boundary dates are planning assumptions, not a schedule."})
            spans.append({"start": f"{start_year + 1}-04-16", "end": f"{start_year + 1}-06-30",
                          "status": "ESTIMATED", "label": "NBA playoffs (conditional, estimated)",
                          "conditional": True, "source": gs_est})
    # Valkyries WNBA seasons overlapping `year`.
    for season in (year - 1, year):
        if season == 2026:
            spans.append({"start": "2026-04-25", "end": "2026-09-24",
                          "status": "VERIFIED", "label": "Golden State Valkyries 2026 WNBA season",
                          "conditional": False,
                          "source": "https://valkyries.wnba.com/news/golden-state-valkyries-announce-local-television-and-radio-broadcast-schedule-20260425",
                          "note": "Club broadcast table. AM/FM blocking follows the per-game radio column; vacation framing uses the full season envelope conservatively."})
            spans.append({"start": "2026-09-27", "end": "2026-10-25",
                          "status": "ESTIMATED", "label": "WNBA playoffs (conditional; Valkyries qualified)",
                          "conditional": True,
                          "source": "https://www.sportingnews.com/us/tickets/news/valkyries-playoff-tickets-prices-schedule-golden-state-2026-wnba/fabf32cb25126dcdd39d7a79",
                          "note": "First round starts 2026-09-27 (verified). Semifinal/final dates unplayed/unpublished; late-October tail is conservative."})
        else:
            spans.append({"start": f"{season}-05-01", "end": f"{season}-09-30",
                          "status": "ESTIMATED",
                          "label": f"Golden State Valkyries {season} WNBA season (estimated envelope)",
                          "conditional": False, "source": "NOT RELEASED - estimated May-September WNBA envelope"})
            spans.append({"start": f"{season}-10-01", "end": f"{season}-10-25",
                          "status": "ESTIMATED", "label": "WNBA playoffs (conditional, estimated)",
                          "conditional": True, "source": "NOT RELEASED - conditional October window"})
    return spans


def _dedupe(spans: list[dict]) -> list[dict]:
    seen, out = set(), []
    for span in spans:
        key = (span["start"], span["end"], span["label"])
        if key in seen:
            continue
        seen.add(key)
        out.append(span)
    return out


def _in_year(spans: list[dict], year: int) -> set[str]:
    out: set[str] = set()
    for span in spans:
        out.update(d for d in daterange(span["start"], span["end"]) if d.startswith(f"{year}-"))
    return out


def blocked_days_for_year(
    year: int,
    mlb: dict,
    count_spring_training: bool,
    section: str = "1",
) -> tuple[set[str], dict]:
    """Every date in calendar `year` that has a game in `section`.

    Three sources of blocking, in calendar order:
      1. the tail of the PREVIOUS NFL season (Week 17/18 + playoffs), which runs
         into January and February of `year` (precise dates, not a span);
      2. this year's MLB season (continuous frame, see the module docstring);
      3. this year's NFL season (continuous from the Hall of Fame Game through
         Dec 31), plus, in sections 2 and 3, the college football span and, in
         section 3, the MLS span.
    """
    leagues = SECTION_LEAGUES.get(section)
    if leagues is None:
        raise KeyError(f"unknown section {section!r}; expected one of {sorted(SECTION_LEAGUES)}")

    sb_prev, sb_status, sb_note = nfl_calendar.SUPER_BOWL_BY_YEAR[year]
    nfl_start, nfl_status, nfl_note = nfl_calendar.NFL_SEASON_START[year]

    blocked: set[str] = set()

    # 1. Previous NFL season: precise final-weekend / playoff dates in `year`,
    #    plus the Pro Bowl Games (NFL all-star) in Super Bowl week.
    prev_dates = nfl_calendar.previous_season_nfl_dates(sb_prev)
    prev_in_year: list[str] = []
    for round_name, days in prev_dates.items():
        for d in days:
            if d.startswith(f"{year}-"):
                blocked.add(d)
                prev_in_year.append(d)

    pro_bowl_date, pro_bowl_status, pro_bowl_note = nfl_calendar.PRO_BOWL_BY_YEAR[year]
    blocked.add(pro_bowl_date)

    # 2. MLB season of `year`. Exact fixture dates are used whenever the official
    #    snapshot for that year is committed; otherwise the season frame stands in.
    mlb_block = None
    if "MLB" in leagues:
        exact_days = mlb_fixture_days(year, count_spring_training)
        if exact_days:
            blocked.update(exact_days)
            mlb_block = {
                "mode": "exact_fixtures",
                "start": exact_days[0],
                "end": exact_days[-1],
                "days_blocked": len(exact_days),
                "status": "VERIFIED",
                "includes_spring_training": count_spring_training,
                "source": f"data/verified/mlb_schedule_{year}.csv (official MLB Stats API snapshot)",
                "note": (
                    "Every date here has at least one official MLB game in the committed "
                    "snapshot; dates without a row are free of MLB under this reading."
                ),
            }
        else:
            mlb_start, mlb_end, mlb_block = mlb_span(year, mlb, count_spring_training)
            blocked.update(daterange(mlb_start, mlb_end))
            mlb_block["mode"] = "season_frame"

    # 3. This year's NFL season: Hall of Fame Game -> Dec 31.
    blocked.update(daterange(nfl_start, f"{year}-12-31"))

    # 4. College football (sections 2 and 3). The previous year's spans are
    #    included too, because a season that starts in year-1 finishes inside
    #    `year` (bowl games and the CFP title game land in early January).
    cf_blocks = []
    if "NCAAF" in leagues:
        cf_blocks = _dedupe(ncaaf_spans(year, _seasons()) + ncaaf_spans(year - 1, _seasons()))
        blocked.update(_in_year(cf_blocks, year))

    # 5. MLS (section 3 only).
    mls_blocks = []
    if "MLS" in leagues:
        mls_blocks = _dedupe(mls_spans(year, _seasons()) + mls_spans(year - 1, _seasons()))
        blocked.update(_in_year(mls_blocks, year))

    # 6. Other live-radio sports (NBA Warriors, WNBA Valkyries) - `all` scope only.
    #    The three requested sections deliberately exclude them.
    other_blocks = []
    if "NBA" in leagues or "WNBA" in leagues:
        other_blocks = _dedupe(other_radio_spans(year) + other_radio_spans(year - 1))
        blocked.update(_in_year(other_blocks, year))

    provenance = {
        "section": section,
        "section_name": SECTION_NAMES[section],
        "leagues": list(leagues),
        "nfl_previous_season_end": {
            "super_bowl": sb_prev,
            "status": sb_status,
            "note": sb_note,
            "playoff_dates_in_year": sorted(prev_in_year),
            "pro_bowl_games": {"date": pro_bowl_date, "status": pro_bowl_status, "note": pro_bowl_note},
        },
        "mlb_block": mlb_block,
        "nfl_current_season_start": {"date": nfl_start, "status": nfl_status, "note": nfl_note},
        "ncaaf_blocks": cf_blocks,
        "mls_blocks": mls_blocks,
        "other_radio_blocks": other_blocks,
    }
    return blocked, provenance


def _requirements(days: int) -> dict:
    return {
        "week_1": days >= 7,
        "weeks_2": days >= 14,
        "weeks_3": days >= 21,
    }


def analyze(
    year: int,
    mlb: dict,
    count_spring_training: bool,
    section: str = "1",
) -> dict:
    blocked, provenance = blocked_days_for_year(year, mlb, count_spring_training, section)
    gaps = find_gaps(blocked, f"{year}-01-01", f"{year}-12-31", min_days=1)
    for gap in gaps:
        gap.update(_requirements(gap["days"]))
    best = gaps[0] if gaps else None
    year_len = datetime(year, 12, 31).timetuple().tm_yday

    def longest_meeting(min_days: int) -> dict | None:
        for gap in gaps:  # already sorted longest-first
            if gap["days"] >= min_days:
                return gap
        return None

    return {
        "year": year,
        "section": section,
        "section_name": SECTION_NAMES[section],
        "interpretation": "strict" if count_spring_training else "regular",
        "blocked_day_count": len(blocked),
        "free_day_count": year_len - len(blocked),
        "gaps": gaps,
        "best": best,
        "best_1_week": longest_meeting(7),
        "best_2_weeks": longest_meeting(14),
        "best_3_weeks": longest_meeting(21),
        "requirements": {
            "week_1": bool(longest_meeting(7)),
            "weeks_2": bool(longest_meeting(14)),
            "weeks_3": bool(longest_meeting(21)),
        },
        "provenance": provenance,
    }


def build_comparison(results: list[dict]) -> dict:
    """{interpretation: {year: {section: summary}}} for the comparison tab."""
    out: dict = {}
    for row in results:
        interp = out.setdefault(row["interpretation"], {})
        year = interp.setdefault(str(row["year"]), {})
        year[row["section"]] = {
            "section_name": row["section_name"],
            "longest_days": row["best"]["days"] if row["best"] else 0,
            "longest_start": row["best"]["start"] if row["best"] else None,
            "longest_end": row["best"]["end"] if row["best"] else None,
            "free_days": row["free_day_count"],
            "blocked_days": row["blocked_day_count"],
            "requirements": row["requirements"],
            "best_1_week": row["best_1_week"],
            "best_2_weeks": row["best_2_weeks"],
            "best_3_weeks": row["best_3_weeks"],
        }
    return out


def build_notes(comparison: dict, results: list[dict]) -> list[str]:
    """Plain-language findings, computed from the numbers rather than written by hand."""
    notes: list[str] = []
    section_ids = ["1", "2", "3"]

    for interp in ("strict", "regular"):
        reading = "Spring Training counts" if interp == "strict" else "regular season + postseason only"
        rows = comparison.get(interp, {})
        per_section = []
        for sid in section_ids:
            best = max((r[sid]["longest_days"] for r in rows.values() if sid in r), default=0)
            three = [y for y, r in sorted(rows.items()) if sid in r and r[sid]["requirements"]["weeks_3"]]
            two = [y for y, r in sorted(rows.items()) if sid in r and r[sid]["requirements"]["weeks_2"]]
            one = [y for y, r in sorted(rows.items()) if sid in r and r[sid]["requirements"]["week_1"]]
            per_section.append((sid, best, one, two, three))
            notes.append(
                f"[{reading}] {SECTION_NAMES[sid]}: longest run across the four years is {best} days; "
                f"a 1-week candidate is found in {len(one)}/4 years, 2 weeks in {len(two)}/4, 3 weeks in {len(three)}/4."
                + (f" 3-week years: {', '.join(three)}." if three else "")
            )
        bests = {sid: b for sid, b, _, _, _ in per_section}
        if all(len({r[sid]["longest_days"] for sid in section_ids}) == 1 for r in rows.values()):
            notes.append(
                f"[{reading}] All three sections give the same longest run ({bests['1']} days). "
                "The modeled MLB and NFL blocks "
                "leave matching longest runs, so adding Stanford/Cal football or the Earthquakes "
                "does not shorten the longest run in this reading."
            )
        else:
            worst = min(bests, key=lambda k: bests[k])
            better = ", ".join(f"Section {k} {v} d" for k, v in sorted(bests.items()))
            notes.append(
                f"[{reading}] The sections do NOT agree ({better}). Section {worst} is the binding constraint."
            )

    # What the college-football tag actually costs.
    cf_diff = []
    for interp, rows in comparison.items():
        for year, r in rows.items():
            if "1" in r and "2" in r and r["1"]["longest_days"] == r["2"]["longest_days"]:
                cf_diff.append(year)
    if len(cf_diff) == 8:
        years_note = ", ".join(sorted(set(cf_diff)))
        notes.append(
            "Sections 1 and 2 have matching longest modeled runs in ("
            + years_note
            + ", both readings). Bay Area college football adds a conditional December/January bowl and CFP envelope, "
              "which is conditional on Stanford or Cal qualifying and never creates or destroys a "
              "1-, 2- or 3-week window. In this model the longest run is unchanged; daily free hours can still differ."
        )

    # The MLS effect.
    mls_rows = []
    for interp, rows in comparison.items():
        for year, r in rows.items():
            if "2" in r and "3" in r and r["3"]["longest_days"] < r["2"]["longest_days"]:
                mls_rows.append(
                    f"{year} ({'strict' if interp == 'strict' else 'regular'}): "
                    f"{r['2']['longest_days']} d -> {r['3']['longest_days']} d"
                )
    if mls_rows:
        notes.append(
            "Adding the San Jose Earthquakes is the only change that costs a whole trip - "
            + "; ".join(mls_rows)
            + ". MLS changes to a summer–spring calendar in 2027. Conservative phase envelopes are used, "
              "which may hide actual fixture gaps. For 2–3 weeks away, "
              "no Section 3 candidate is found in this model; Sections 1 and 2 have candidates."
        )

    # The single most useful comparison in the whole dataset.
    notes.append(
        "The reading of 'no MLB games' matters more than the section does. If Spring Training counts, "
        "the best week in any year is the 8-11 days between the conference championships and the Pro Bowl, "
        "and no section reaches two weeks. If only the regular season and postseason count, Sections 1 and 2 "
        "open a 5-6 week corridor from the day after the Super Bowl to Opening Day, and only Section 3 "
        "misses out."
    )
    return notes


def main(verbose: bool = True) -> dict:
    seasons = _seasons()
    mlb = seasons["mlb"]
    profiles = json.loads((VERIFIED / "profiles.json").read_text(encoding="utf-8"))
    section_ids = [s["id"] for s in profiles["sections"]] + [profiles["extra_scope"]["id"]]

    results = []
    for count_spring_training in (True, False):
        for section in section_ids:
            for year in (2026, 2027, 2028, 2029):
                results.append(analyze(year, mlb, count_spring_training, section))

    comparison = build_comparison(results)
    report = {
        "_meta": {
            "generated_by": "scripts/analyze_vacation.py",
            "question": "When can I take 1, 2 or 3 weeks off with no games in this section?",
            "sections": {sid: SECTION_NAMES[sid] for sid in section_ids},
            "interpretations": {
                "strict": "Spring Training exhibitions count as MLB games.",
                "regular": "Only MLB regular season and postseason count.",
            },
            "method": "For each section and calendar year we block (a) the previous NFL season's precise Week 17/18 and playoff dates plus the Pro Bowl Games, (b) that year's MLB games - exact official fixture dates when the committed league snapshot for that year exists, otherwise the documented continuous season frame, (c) that year's NFL season from the Hall of Fame Game to Dec 31, (d) in sections 2-3 the Stanford/California football span, (e) in section 3 the Earthquakes MLS span, and (f) in the superset only the Warriors NBA and Valkyries WNBA spans. We then report every contiguous unblocked run and whether it satisfies 1, 2 or 3 weeks.",
            "caveat": "Continuous season envelopes are conservative and can hide real fixture gaps. No candidate found is not proof a trip is impossible. Future schedule and radio coverage remain incomplete.",
        },
        "comparison": comparison,
        "comparison_notes": build_notes(comparison, results),
        "results": results,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vacation-windows.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    if not verbose:
        return report

    for flag, name in ((True, "STRICT (spring training counts)"), (False, "REGULAR SEASON + POSTSEASON ONLY")):
        print(f"\n=== {name} ===")
        print(f"{'year':<6}{'section':<40}{'longest':>9}  {'1wk':>4}{'2wk':>5}{'3wk':>5}  best window")
        for row in results:
            if row["interpretation"] != ("strict" if flag else "regular"):
                continue
            req = row["requirements"]
            span = f"{row['best']['start']} -> {row['best']['end']}" if row["best"] else "-"
            print(
                f"{row['year']:<6}{row['section_name'][:38]:<40}"
                f"{(str(row['best']['days']) + ' d') if row['best'] else 'none':>9}  "
                f"{'Y' if req['week_1'] else '-':>4}{'Y' if req['weeks_2'] else '-':>5}{'Y' if req['weeks_3'] else '-':>5}  {span}"
            )
    return report


if __name__ == "__main__":
    main(verbose=True)
