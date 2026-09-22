"""The NFL league calendar, 2026-2029, with an explicit provenance status on every date.

One source of truth. Both the data builder (which needs day-board records for the
playoff rounds) and the vacation analysis (which needs the blocked date set) import
from here, so the two can never disagree about when the NFL plays.

Status legend
-------------
VERIFIED
    Read from an NFL-owned or club-owned source on the retrieval date.
    * Super Bowl LXI  2027-02-14  club/league key-dates release (seahawks.com, 2026-07-07)
    * Super Bowl LXII 2028-02-13  NFL announcement, Mercedes-Benz Stadium
    * 2026-27 playoff rounds       same key-dates release
    * Pro Bowl Games 2026-02-03    operations.nfl.com, 2025-10-22
ESTIMATED
    NOT released by the NFL. Derived from the day-of-week-stable offsets measured
    from the verified 2026-27 cycle. Never presented as a real schedule.

Why the offsets are trustworthy for the *vacation* question
-----------------------------------------------------------
Every round is anchored to a Super Bowl date. 2027 and 2028 are official inputs;
2029 (Super Bowl LXIII) keeps the second-Sunday-of-February planning date
2029-02-11 as an ESTIMATE: the league's own 2026-03-30 announcement names the
host and year but no exact day, and NBC reported the game "does not yet have a
firm date" (see IR-12). Super Bowl LXIV in 2030 is likewise an estimate. The
offsets (Wild Card = SB-29/28/27, Divisional = SB-22/21, Conference
Championships = SB-14) reproduce the verified 2026-27 layout exactly; a test
asserts that. A shift of one week in any future round would move a blocked date,
so the analysis output labels every future-year row ESTIMATED.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Verified / estimated anchors
# ---------------------------------------------------------------------------

#: {calendar year of the Super Bowl: (ISO date, status, note)}
SUPER_BOWL_BY_YEAR = {
    2026: ("2026-02-08", "VERIFIED", "Super Bowl LX, Levi's Stadium, Santa Clara CA"),
    2027: ("2027-02-14", "VERIFIED", "Super Bowl LXI, SoFi Stadium, Inglewood CA"),
    2028: ("2028-02-13", "VERIFIED", "Super Bowl LXII, Mercedes-Benz Stadium, Atlanta GA"),
    2030: (
        "2030-02-10",
        "ESTIMATED",
        "Super Bowl LXIV - the NFL has announced neither a site nor a date. "
        "Estimated as the second Sunday of February 2030 so the 2029 season has a close.",
    ),
    2029: (
        "2029-02-11",
        "ESTIMATED",
        "Super Bowl LXIII, Allegiant Stadium, Las Vegas NV - host and year are "
        "official (NFL Annual Meeting, Phoenix, 2026-03-30) but secondary sources "
        "conflict on the exact day: WJHL/KLAS (Nexstar, 2026-03-30) reports the "
        "NFL announced Feb 11, 2029, while NBC reported that the "
        "game 'does not yet have a firm date', the league's own nfl.com release "
        "names no day, and the Forbes URL once cited here returns 404. Per the "
        "project rule the league-owned source wins on conflict, so 2029-02-11 "
        "stays the second-Sunday-of-February planning assumption, not a released "
        "date. Re-check before booking far out. See docs/IRREGULARITIES.md IR-12.",
    ),
}

#: When the NFL season starts occupying the calendar: the Hall of Fame Game.
NFL_SEASON_START = {
    2026: ("2026-08-06", "VERIFIED", "Hall of Fame Game, per the NFL/ESPN league calendar"),
    2027: ("2027-08-05", "ESTIMATED", "Not released - same Thursday-of-first-full-August-week pattern"),
    2028: ("2028-08-03", "ESTIMATED", "Not released"),
    2029: ("2029-08-02", "ESTIMATED", "Not released"),
}

#: Kickoff of the regular season (the Wednesday/Thursday opener).
REGULAR_SEASON_START = {
    2026: ("2026-09-09", "VERIFIED", "NFL Kickoff Weekend: Seahawks host Patriots (Wednesday), then the 49ers-Rams Melbourne game on 2026-09-10"),
    2027: ("2027-09-09", "ESTIMATED", "Not released - Thursday after Labor Day"),
    2028: ("2028-09-07", "ESTIMATED", "Not released - Thursday after Labor Day"),
    2029: ("2029-09-06", "ESTIMATED", "Not released - Thursday after Labor Day"),
}

#: Days of the week the NFL regularly plays on, by Python weekday() number
#: (0 = Monday). Used to place season-frame records so a Sunday inside the NFL
#: season can never read as free just because Westwood One has not published its
#: national window yet. Saturdays are added in December only (Week 15-17
#: Saturday doubleheaders), because January Saturdays are covered by the playoff
#: round records.
NFL_REGULAR_WEEKDAYS = (
    6,  # Sunday
    0,  # Monday
    3,  # Thursday
)
NFL_SATURDAY_MONTHS = (12, 1)

# The 2026 official release is available, so keep the Saturday set exact rather
# than treating every December Saturday as an NFL date (there is no game on
# 2026-12-05, for example). Future seasons remain estimates and use the broader
# month/day-of-week pattern below.
KNOWN_SATURDAY_DATES = {
    2026: ("2026-12-19", "2027-01-02", "2027-01-09"),
}


def _official_2026_game_dates() -> list[str]:
    """Exact 2026 regular-season date set from the checked-in official snapshot.

    Preseason occupancy comes from the 49ers source, not from every other NFL
    preseason game. This keeps the verified season calendar from inventing shape-only
    dates such as an NFL Thursday on 2027-01-07.  The CSV is deliberately a small source input;
    the 272 matchup records themselves are loaded by build_data.py.
    """
    path = Path(__file__).resolve().parents[1] / "data" / "verified" / "nfl_regular_2026.csv"
    dates: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("|")
        if len(fields) != 5:
            continue
        _, date_local, _, _, _ = fields
        if date_local != "TBD":
            dates.add(date_local)
    # Four flexible games in Weeks 16/17 and all Week 18 games have official
    # Saturday/Sunday windows even though individual assignments are unresolved.
    dates.update(("2026-12-26", "2027-01-02", "2027-01-09", "2027-01-10"))
    return sorted(dates)


def regular_season_end(season_year: int) -> str:
    """Week 18 Sunday: the last day of the regular season for `season_year`."""
    sb_iso, _, _ = super_bowl_for_season(season_year)
    return (datetime.strptime(sb_iso, "%Y-%m-%d").date() - timedelta(days=35)).isoformat()


def season_game_dates(season_year: int) -> list[str]:
    """Every date on which the NFL is scheduled to play in `season_year`'s season.

    Deliberately date-level: the project does not bundle all 272 games, but it does
    know the shape of the NFL week, which is enough to stop the day board from
    reporting an NFL Sunday as free.
    """
    if season_year == 2026:
        return _official_2026_game_dates()

    start_iso, _, _ = NFL_SEASON_START[season_year]
    end_iso = regular_season_end(season_year)
    day = datetime.strptime(start_iso, "%Y-%m-%d").date()
    stop = datetime.strptime(end_iso, "%Y-%m-%d").date()
    out = [REGULAR_SEASON_START[season_year][0]]
    while day <= stop:
        is_saturday = (
            day.isoformat() in KNOWN_SATURDAY_DATES.get(season_year, ())
            if season_year in KNOWN_SATURDAY_DATES
            else day.weekday() == 5 and day.month in NFL_SATURDAY_MONTHS
        )
        if day.weekday() in NFL_REGULAR_WEEKDAYS or is_saturday:
            out.append(day.isoformat())
        day += timedelta(days=1)
    # The regular-season opener is normally one of the weekdays above; a
    # Wednesday opener (2026) is not, which is why it is listed explicitly.
    return sorted(set(out))


def _need_datetime():
    return datetime


# The Pro Bowl Games (NFL all-star). Moved into Super Bowl week from the 2025-26
#: cycle: the AFC-vs-NFC flag game is the Tuesday of Super Bowl week.
PRO_BOWL_BY_YEAR = {
    2026: ("2026-02-03", "VERIFIED", "2026 Pro Bowl Games, Moscone Center, San Francisco (NFL announcement 2025-10-22)"),
    2027: ("2027-02-09", "ESTIMATED", "Tuesday of Super Bowl LXI week at SoFi Stadium (pattern, not officially confirmed)"),
    2028: ("2028-02-08", "ESTIMATED", "Tuesday of Super Bowl LXII week (pattern, not officially confirmed)"),
    2029: ("2029-02-06", "ESTIMATED", "Tuesday of Super Bowl LXIII week (pattern, not officially confirmed)"),
    2030: ("2030-02-05", "ESTIMATED", "Tuesday of Super Bowl LXIV week (pattern, not officially confirmed)"),
}

#: Days BEFORE the Super Bowl that each round of *that* season lands on, measured
#: from the verified 2026-27 layout (Super Bowl Sunday 2027-02-14):
#:   Week 17 Sat/Sun, Week 18 Sat/Sun + SNF, Wild Card Sat/Sun/Mon,
#:   Divisional Sat/Sun, Conference Championship Sun, Super Bowl Sun.
ROUND_OFFSETS = {
    "Week 17": [43, 42, 41],
    "Week 18": [36, 35],
    "Wild Card": [29, 28, 27],
    "Divisional": [22, 21],
    "Conference Championships": [14],
    "Super Bowl": [0],
}

#: Rounds whose games Westwood One carries nationally, i.e. rounds that are certain
#: to be live on Bay Area radio regardless of which clubs qualify.
WESTWOOD_ONE_NATIONAL_ROUNDS = ("Wild Card", "Divisional", "Conference Championships", "Super Bowl")


def _d(iso: str) -> date:
    return datetime.strptime(iso, "%Y-%m-%d").date()


def previous_season_nfl_dates(sb_iso: str) -> dict[str, list[str]]:
    """Round -> the ISO dates of the season that ENDS at `sb_iso`.

    Offsets are day-of-week stable, which is what makes this transferable to a
    future cycle whose Super Bowl date is already official.
    """
    sb = _d(sb_iso)
    return {
        name: sorted((sb - timedelta(days=o)).isoformat() for o in offsets)
        for name, offsets in ROUND_OFFSETS.items()
    }


def playoff_round_dates(sb_iso: str, round_name: str) -> list[str]:
    return previous_season_nfl_dates(sb_iso)[round_name]


def super_bowl_for_season(season_year: int) -> tuple[str, str, str]:
    """The Super Bowl that closes the season starting in `season_year`.

    The 2026 season ends with the February 2027 Super Bowl.
    """
    return SUPER_BOWL_BY_YEAR[season_year + 1]


def verify_template_against_2026_27() -> dict[str, list[str]]:
    """The offsets above must reproduce the NFL's own published 2026-27 dates.

    NFL key dates (seahawks.com, 2026-07-07): Wild Card 2027-01-16..18,
    Divisional 2027-01-23..24, Championships 2027-01-31, Super Bowl 2027-02-14.
    """
    sb = SUPER_BOWL_BY_YEAR[2027][0]
    return {
        "Wild Card": playoff_round_dates(sb, "Wild Card"),
        "Divisional": playoff_round_dates(sb, "Divisional"),
        "Conference Championships": playoff_round_dates(sb, "Conference Championships"),
        "Super Bowl": playoff_round_dates(sb, "Super Bowl"),
    }
