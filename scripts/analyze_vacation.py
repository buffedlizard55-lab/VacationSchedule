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

Blocking model
--------------
* MLB blocks continuously from its first game (Spring Training, strict) or its
  regular-season opener (regular) through the end of the postseason. MLB plays on
  essentially every one of those dates, so a continuous span is the honest,
  conservative choice.
* NFL blocks on the *actual* days games are played, not a continuous span. The
  January-February portion of the NFL calendar is sparse (Week 17/18, then four
  single-weekend playoff rounds plus the Super Bowl), so treating it as one
  continuous block wrongly hid real clean windows (e.g. the week between Week 18
  and Wild Card Weekend, and the Pro Bowl week before the Super Bowl).
  - The 2026-27 cycle (Super Bowl LXI, 2027-02-14, VERIFIED) is used as the
    day-of-week template. For earlier/future cycles every round date is derived
    from that cycle's Super Bowl date and labelled VERIFIED (when the NFL has
    published the date) or ESTIMATED (when it has not).
* The NFL's Pro Bowl Games (~1 week before the Super Bowl) are NOT blocked
  because no verified per-year date exists at retrieval time; they are flagged in
  the irregularities instead. Treat any "free" window that straddles early
  February accordingly.
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
#: LX (2026), LXI (2027) and LXII (2028) are league-verified; LXIII (2029) is a
#: partial verification -- Las Vegas is official, the exact day is estimated as
#: the 2nd Sunday of February.
SUPER_BOWL_BY_YEAR = {
    2026: ("2026-02-08", "VERIFIED", "Super Bowl LX, Levi's Stadium, Santa Clara CA"),
    2027: ("2027-02-14", "VERIFIED", "Super Bowl LXI, SoFi Stadium, Inglewood CA"),
    2028: ("2028-02-13", "VERIFIED", "Super Bowl LXII, Mercedes-Benz Stadium, Atlanta GA"),
    2029: ("2029-02-11", "ESTIMATED", "Super Bowl LXIII, Allegiant Stadium, Las Vegas NV - month official, day estimated (2nd Sunday of Feb 2029)"),
}

#: When the current year's NFL season STARTS occupying the calendar.
NFL_SEASON_START = {
    2026: ("2026-08-06", "VERIFIED", "Hall of Fame Game, per the NFL/ESPN league calendar"),
    2027: ("2027-08-05", "ESTIMATED", "Not released"),
    2028: ("2028-08-03", "ESTIMATED", "Not released"),
    2029: ("2029-08-02", "ESTIMATED", "Not released"),
}

#: The NFL Pro Bowl Games moved to Super Bowl week starting with the 2025-26
#: cycle (announced by the NFL 2025-10-22): the AFC-vs-NFC flag game is the
#: Tuesday before the Super Bowl. 2026 is VERIFIED (2026-02-03, Moscone Center,
#: SF). 2027+ follow the same Tuesday-of-Super-Bowl-week pattern and are flagged
#: ESTIMATED until the NFL publishes them. The user listed "NFL all star games"
#: as busy, so these block.
PRO_BOWL_BY_YEAR = {
    2026: ("2026-02-03", "VERIFIED", "2026 Pro Bowl Games, Moscone Center, San Francisco (NFL announcement 2025-10-22)"),
    2027: ("2027-02-09", "ESTIMATED", "Tuesday of Super Bowl LXI week at SoFi Stadium (pattern, not officially confirmed)"),
    2028: ("2028-02-08", "ESTIMATED", "Tuesday of Super Bowl LXII week (pattern, not officially confirmed)"),
    2029: ("2029-02-06", "ESTIMATED", "Tuesday of Super Bowl LXIII week (pattern, not officially confirmed)"),
}

#: Days-before-the-Super-Bowl for each round of the PREVIOUS season's schedule,
#: measured from the verified 2026-27 layout (Super Bowl Sun 2027-02-14):
#:   Week 17 Sat/Sun, Week 18 Sat/Sun, Wild Card Sat/Sun/Mon, Divisional
#:   Sat/Sun, Conference Championships Sun, Super Bowl Sunday.
#: The offsets are day-of-week stable, so they transfer to other cycles.
PREV_SEASON_ROUND_OFFSETS = {
    "Week 17": [43, 42, 41],
    "Week 18": [36, 35],
    "Wild Card": [29, 28, 27],
    "Divisional": [22, 21],
    "Conference Championships": [14],
    "Super Bowl": [0],
}


def daterange(start: str, end: str) -> list[str]:
    day = datetime.strptime(start, "%Y-%m-%d").date()
    stop = datetime.strptime(end, "%Y-%m-%d").date()
    out = []
    while day <= stop:
        out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def previous_season_nfl_dates(sb_iso: str) -> dict[str, list[str]]:
    """The NFL dates of the season that ENDS at `sb_iso`, per round.

    Returns a dict round -> [ISO dates] reverse-chronological, using the
    day-of-week-stable offsets measured from the verified 2026-27 cycle.
    """
    sb = datetime.strptime(sb_iso, "%Y-%m-%d").date()
    out: dict[str, list[str]] = {}
    for round_name, offsets in PREV_SEASON_ROUND_OFFSETS.items():
        out[round_name] = sorted((sb - timedelta(days=o)).isoformat() for o in offsets)
    return out


def blocked_days_for_year(year: int, mlb: dict, count_spring_training: bool) -> tuple[set[str], dict]:
    """Every date in calendar `year` that has an MLB or NFL game.

    Three sources of blocking, in calendar order:
      1. the tail of the PREVIOUS NFL season (Week 17/18 + playoffs), which runs
         into January and February of `year` (precise dates, not a span);
      2. this year's MLB season (continuous, see module docstring);
      3. this year's NFL season (continuous from the Hall of Fame Game to
         Dec 31 -- late-season Tuesday/Wednesday over-blocking is accepted as
         conservative and is documented).
    """
    frame = mlb[str(year)]
    sb_prev, sb_status, sb_note = SUPER_BOWL_BY_YEAR[year]
    nfl_start, nfl_status, nfl_note = NFL_SEASON_START[year]

    blocked: set[str] = set()

    # 1. previous NFL season: precise playoff / final-weekend dates in `year`,
    #    plus the Pro Bowl Games (NFL all-star) in Super Bowl week.
    prev_dates = previous_season_nfl_dates(sb_prev)
    prev_in_year: list[str] = []
    for round_name, days in prev_dates.items():
        for d in days:
            if d.startswith(f"{year}-"):
                blocked.add(d)
                prev_in_year.append(d)

    pro_bowl_date, pro_bowl_status, pro_bowl_note = PRO_BOWL_BY_YEAR[year]
    blocked.add(pro_bowl_date)

    # 2. MLB season of `year`.
    mlb_start = frame["spring_training_start"] if count_spring_training else frame["regular_season_start"]
    blocked.update(daterange(mlb_start, frame["postseason_end"]))

    # 3. this year's NFL season: Hall of Fame Game -> Dec 31.
    blocked.update(daterange(nfl_start, f"{year}-12-31"))

    provenance = {
        "nfl_previous_season_end": {
            "super_bowl": sb_prev,
            "status": sb_status,
            "note": sb_note,
            "playoff_dates_in_year": sorted(prev_in_year),
            "pro_bowl_games": {"date": pro_bowl_date, "status": pro_bowl_status, "note": pro_bowl_note},
        },
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
    year_len = datetime(year, 12, 31).timetuple().tm_yday
    # `blocked` is a set, so dates that are both MLB and NFL blocked are counted
    # once. (A previous version summed overlapping slices and inflated the
    # blocked count; this also kept the free-day denominator honest.)
    return {
        "year": year,
        "interpretation": "strict" if count_spring_training else "regular",
        "blocked_day_count": len(blocked),
        "free_day_count": year_len - len(blocked),
        "gaps": gaps,
        "best": best,
        "provenance": provenance,
    }


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
            "method": "For each calendar year we block (a) the previous NFL season's precise Week 17/18 and playoff dates, (b) that year's MLB season as a continuous span, and (c) that year's NFL season from the Hall of Fame Game to Dec 31, then report the contiguous unblocked runs. NFL Pro Bowl Games are not blocked (no verified date) and are flagged in docs/IRREGULARITIES.md.",
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
