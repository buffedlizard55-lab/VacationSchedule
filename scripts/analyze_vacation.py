"""Compute the best vacation windows for 2026-2029 and emit machine + human output.

Run:  python3 scripts/analyze_vacation.py

Two interpretations are computed on purpose, because the answer changes a lot
depending on whether MLB Spring Training counts as "an MLB game":

  strict   - any MLB game blocks, including Spring Training exhibitions.
             Spring Training games ARE MLB games (gameType 'S' in the Stats API)
             and several are broadcast, so this is the literal reading.
  regular  - only MLB regular season + postseason block. Spring Training is
             treated as exhibition baseball and ignored.

Both are reported. Neither is presented as the only correct answer.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from lib_windows import find_gaps

ROOT = Path(__file__).resolve().parent.parent
VERIFIED = ROOT / "data" / "verified"
OUT = ROOT / "data" / "analysis"

#: Super Bowl dates that CLOSE the previous NFL season, by calendar year.
#: 2026 (LX) and 2027 (LXI) and 2028 (LXII) are league-verified; 2029 is an
#: estimate anchored to the officially announced Las Vegas site.
SUPER_BOWL_BY_YEAR = {
    2026: ("2026-02-08", "VERIFIED", "Super Bowl LX, Levi's Stadium, Santa Clara CA"),
    2027: ("2027-02-14", "VERIFIED", "Super Bowl LXI, SoFi Stadium, Inglewood CA"),
    2028: ("2028-02-13", "VERIFIED", "Super Bowl LXII, Mercedes-Benz Stadium, Atlanta GA"),
    2029: ("2029-02-11", "ESTIMATED", "Super Bowl LXIII, Allegiant Stadium, Las Vegas NV - month official, day estimated (2nd Sunday of Feb 2029)"),
}

#: When the current year's NFL season STARTS occupying the calendar.
NFL_SEASON_START = {
    2026: ("2026-08-06", "VERIFIED", "Hall of Fame Game, per the ESPN league calendar"),
    2027: ("2027-08-05", "ESTIMATED", "Not released"),
    2028: ("2028-08-03", "ESTIMATED", "Not released"),
    2029: ("2029-08-02", "ESTIMATED", "Not released"),
}


def daterange(start: str, end: str) -> list[str]:
    day = datetime.strptime(start, "%Y-%m-%d").date()
    stop = datetime.strptime(end, "%Y-%m-%d").date()
    out = []
    while day <= stop:
        out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def blocked_days_for_year(year: int, mlb: dict, count_spring_training: bool) -> tuple[set[str], dict]:
    """Every date in calendar `year` that has an MLB or NFL game.

    Three sources of blocking, in calendar order:
      1. the tail of the PREVIOUS NFL season, which ends at that season's
         Super Bowl in February of `year`;
      2. this year's MLB season;
      3. this year's NFL season, which starts with the Hall of Fame Game in
         August and runs past New Year's Eve.
    """
    frame = mlb[str(year)]
    sb_prev, sb_status, sb_note = SUPER_BOWL_BY_YEAR[year]
    nfl_start, nfl_status, nfl_note = NFL_SEASON_START[year]

    blocked: set[str] = set()

    # 1. previous NFL season: Jan 1 -> Super Bowl of `year`
    blocked.update(daterange(f"{year}-01-01", sb_prev))

    # 2. MLB season of `year`
    mlb_start = frame["spring_training_start"] if count_spring_training else frame["regular_season_start"]
    blocked.update(daterange(mlb_start, frame["postseason_end"]))

    # 3. this year's NFL season: Hall of Fame Game -> Dec 31
    blocked.update(daterange(nfl_start, f"{year}-12-31"))

    provenance = {
        "nfl_previous_season_end": {"date": sb_prev, "status": sb_status, "note": sb_note},
        "mlb_block": {
            "start": mlb_start,
            "end": frame["postseason_end"],
            "status": frame["status"],
            "includes_spring_training": count_spring_training,
        },
        "nfl_current_season_start": {"date": nfl_start, "status": nfl_status, "note": nfl_note},
    }
    return blocked, provenance


def analyze(year: int, mlb: dict, count_spring_training: bool) -> dict:
    blocked, provenance = blocked_days_for_year(year, mlb, count_spring_training)
    gaps = find_gaps(blocked, f"{year}-01-01", f"{year}-12-31", min_days=1)
    best = gaps[0] if gaps else None
    return {
        "year": year,
        "interpretation": "strict" if count_spring_training else "regular",
        "blocked_day_count": len(blocked),
        "free_day_count": 366 - len(blocked) if _is_leap(year) else 365 - len(blocked),
        "gaps": gaps,
        "best": best,
        "provenance": provenance,
    }


def _is_leap(year: int) -> bool:
    return date(year, 12, 31).toordinal() - date(year, 1, 1).toordinal() + 1 == 366


def main(verbose: bool = True) -> dict:
    seasons = json.loads((VERIFIED / "seasons.json").read_text(encoding="utf-8"))
    mlb = seasons["mlb"]

    results = []
    for interpretation_flag in (True, False):
        for year in (2026, 2027, 2028, 2029):
            results.append(analyze(year, mlb, interpretation_flag))

    report = {
        "_meta": {
            "generated_by": "scripts/analyze_vacation.py",
            "question": "When can I take 1, 2 or 3 weeks off with no MLB and no NFL games scheduled?",
            "interpretations": {
                "strict": "Spring Training exhibitions count as MLB games.",
                "regular": "Only MLB regular season and postseason count.",
            },
            "method": "For each calendar year we union three blocking spans - the tail of the previous NFL season up to its Super Bowl, that year's MLB season, and that year's NFL season from the Hall of Fame Game to Dec 31 - then report the contiguous unblocked runs.",
        },
        "results": results,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vacation-windows.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    # Console summary - the numbers in docs/VACATION-WINDOWS.md come from here.
    if not verbose:
        return report
    for interpretation_flag, name in ((True, "STRICT (spring training counts)"), (False, "REGULAR SEASON + POSTSEASON ONLY")):
        print(f"\n=== {name} ===")
        for row in results:
            if row["interpretation"] != ("strict" if interpretation_flag else "regular"):
                continue
            best = row["best"]
            if best:
                print(
                    f"{row['year']}: longest clean run = {best['days']} days "
                    f"({best['start']} -> {best['end']}, {best['weeks']} weeks); "
                    f"{row['free_day_count']} free days total in the year"
                )
            else:
                print(f"{row['year']}: NO free day at all")
    return report


if __name__ == "__main__":
    main(verbose=True)
