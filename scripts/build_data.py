"""Normalize every verified source into one flat game list, then emit the data
bundle consumed by the web app.

Run:  python3 scripts/build_data.py

Design rules
------------
* Nothing in this file invents a start time. If a source did not publish one,
  the game is emitted with `time_status: "TBD"` and the caller must apply the
  documented TBD envelope (see docs/METHODOLOGY.md) or report it as unresolved.
* Every emitted game carries `source` so a human can re-verify it by hand.
* Deduplication is by (league, date_local, opponent-pair), because the 129th Big
  Game appears once under Stanford and once under Cal.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import nfl_calendar
from lib_windows import DEFAULT_DURATIONS, MLB_TBD_SENTINEL_UTC, USER_TZ

ROOT = Path(__file__).resolve().parent.parent
VERIFIED = ROOT / "data" / "verified"
OUT_DIR = ROOT / "site" / "data"

# Eastern Time is what Westwood One and the NCAA sources publish in.
ET = ZoneInfo("America/New_York")

#: Window applied to a game whose date is verified but whose kickoff is not.
#: Conservative on purpose: it blocks the whole plausible broadcast envelope so
#: a vacation is never recommended on a day that might actually be busy.
#:
#: Single source of truth lives in lib_windows.TBD_ENVELOPE_PT (which also carries
#: the MLB entry the runtime engine needs). Imported, not redeclared, so the builder
#: and the engine cannot drift apart.
from lib_windows import TBD_ENVELOPE_PT  # noqa: E402

TBD_ENVELOPE = {k: tuple(v) for k, v in TBD_ENVELOPE_PT.items()}


def load(name: str) -> dict:
    with (VERIFIED / name).open(encoding="utf-8") as handle:
        return json.load(handle)


NFL_TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

NFL_FULL_SCHEDULE_SOURCE = "https://www.nfl.com/nfl-schedule-release/"
NFL_FULL_SCHEDULE_PDF = (
    "https://media.nfl.com/content/dam/communications/football-communications/2026/news/"
    "05%2014%2026%20-%202026%20NFL%20Schedule%20-%20By%20Week.pdf"
)


def load_nfl_regular_schedule() -> list[dict]:
    """Load the 272-game 2026 regular-season schedule snapshot.

    The NFL publishes kickoff times in Eastern Time in its by-week release.  The
    Week 16/17 flexible matchups and Week 18 matchups are official, but their date
    and/or kickoff fields are intentionally still TBD in the source; those rows
    retain ``None`` rather than borrowing a date from a third-party feed.  This is a reference schedule, not a radio claim:
    Westwood One's national selection remains the only NFL interval counted by
    Sections 1-3.
    """
    rows: list[dict] = []
    path = VERIFIED / "nfl_regular_2026.csv"
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise ValueError(f"{path}:{line_no}: expected 5 pipe-separated fields")
        week, date_local, kickoff_et, away, home = fields
        if away not in NFL_TEAM_NAMES or home not in NFL_TEAM_NAMES:
            raise ValueError(f"{path}:{line_no}: unknown NFL team {away}/{home}")
        is_tbd = date_local == "TBD" or kickoff_et == "TBD"
        rows.append({
            "week": int(week),
            "date_local": None if date_local == "TBD" else date_local,
            "date_window": {
                16: ["2026-12-26", "2026-12-27"],
                17: ["2027-01-02", "2027-01-03"],
                18: ["2027-01-09", "2027-01-10"],
            }.get(int(week)) if is_tbd else None,
            "kickoff_et": None if kickoff_et == "TBD" else kickoff_et,
            "away": NFL_TEAM_NAMES[away],
            "home": NFL_TEAM_NAMES[home],
            "away_abbr": away,
            "home_abbr": home,
            "label": f"{NFL_TEAM_NAMES[away]} at {NFL_TEAM_NAMES[home]}",
            "time_status": "TBD_official_window" if is_tbd else "official",
            "source": NFL_FULL_SCHEDULE_PDF,
        })
    if len(rows) != 272:
        raise ValueError(f"2026 NFL schedule contains {len(rows)} rows, expected 272")
    if len({(g["week"], g["away_abbr"], g["home_abbr"]) for g in rows}) != 272:
        raise ValueError("2026 NFL schedule contains duplicate game keys")
    appearances = {
        abbr: sum(abbr in (g["away_abbr"], g["home_abbr"]) for g in rows)
        for abbr in NFL_TEAM_NAMES
    }
    if set(appearances.values()) != {17}:
        raise ValueError(f"2026 NFL schedule team appearance counts are not all 17: {appearances}")
    return rows


# ---------------------------------------------------------------------------
# Coverage sections
# ---------------------------------------------------------------------------


def load_profiles() -> dict:
    """The three sections the user asked to compare (verbatim definitions)."""
    return load("profiles.json")


def sections_for_tags(tags: list[str], profiles: dict) -> list[str]:
    """Which sections a game belongs to, given its tags.

    Section 2's tag set is a superset of Section 1's and Section 3's of Section 2's,
    so a Stanford game lands in [2, 3] and a Westwood One national NCAA game lands
    in [] -- it is tracked by the project but is NOT part of any of the three
    sections, because the request lists Westwood One for the NFL only.
    """
    out = []
    for section in profiles["sections"]:
        if any(tag in section["required_tags"] for tag in tags):
            out.append(section["id"])
    return out



def et_to_utc(date_local: str, hhmm: str) -> str:
    """Convert an Eastern-time wall-clock time to UTC ISO (DST-aware)."""
    moment = datetime.strptime(f"{date_local}T{hhmm}:00", "%Y-%m-%dT%H:%M:%S")
    aware = moment.replace(tzinfo=ET, fold=0)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pt_to_utc(date_local: str, hhmm: str) -> str:
    """Local Pacific wall-clock -> UTC ISO (DST-aware)."""
    moment = datetime.strptime(f"{date_local}T{hhmm}:00", "%Y-%m-%dT%H:%M:%S")
    aware = moment.replace(tzinfo=USER_TZ, fold=0)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_to_local_date(utc_iso: str) -> str:
    return datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    ).astimezone(USER_TZ).date().isoformat()


# ---------------------------------------------------------------------------
# Per-source normalizers
# ---------------------------------------------------------------------------


def from_westwood_one() -> tuple[list[dict], list[dict]]:
    payload = load("nfl_westwoodone_2026.json")
    source = payload["_meta"]["source"]
    games, unresolved = [], []
    official = {(g["date_local"], g["away"], g["home"]): g for g in load_nfl_regular_schedule()}
    for row in payload["games"]:
        league = row.get("league", "NFL")
        # Westwood One's NFL page also lists one NCAA football broadcast
        # (LSU@Ole Miss). Those are handled by from_westwood_one_ncaaf() with
        # the full NCAA schedule, so skip them here to avoid double-blocking.
        if league != "NFL":
            continue
        label = f"{row['away']} at {row['home']}"
        if row.get("tbd_teams"):
            label = f"{row['feed']} (teams TBA)"
        game = {
            "league": league,
            "label": label,
            "detail": row["feed"],
            "venue": row.get("venue", ""),
            "priority": "high",
            "source": row.get("url") or source,
            "network": "Westwood One national feed · local AM/FM assignment unconfirmed",
            "date_local": row["date_local"],
            "radio_air_utc": et_to_utc(row["date_local"], row["published_et"]),
            "start_utc": et_to_utc(row["date_local"], row["published_et"]),
            "duration": DEFAULT_DURATIONS[league],
            "time_status": "published_air_time",
            "tags": ["NFL:national"],
        }
        # Where a team-published kickoff exists and differs from the Westwood
        # One air time, keep both: the engine blocks from the earlier instant.
        if row.get("official_kickoff_pt"):
            game["start_utc"] = pt_to_utc(row["date_local"], row["official_kickoff_pt"])
            game["time_status"] = "official_kickoff_plus_radio_air_time"
            game["time_conflict"] = True
        fixture = official.get((row["date_local"], row["away"], row["home"]))
        if fixture and fixture.get("kickoff_et"):
            game["start_utc"] = et_to_utc(fixture["date_local"], fixture["kickoff_et"])
            game["time_status"] = "official_kickoff_plus_radio_air_time"
            game["kickoff_source"] = fixture["source"]
        elif not row.get("official_kickoff_pt"):
            # Air time is not kickoff. Reserve an explicit pregame allowance;
            # never describe air time + average duration as an exact finish.
            game["duration"] += 90
            game["detail"] += " · kickoff unresolved; 90-minute planning allowance added"
        games.append(game)
        if row.get("tbd_teams"):
            unresolved.append({
                "league": league, "date_local": row["date_local"], "label": label,
                "reason": "Westwood One has not announced the teams for this slot.",
                "source": row.get("url", source),
            })
    return games, unresolved


def from_49ers() -> tuple[list[dict], list[dict]]:
    payload = load("bay_area_2026.json")["nfl_49ers"]
    source = payload["source"]
    games, unresolved = [], []
    for row in payload["games"]:
        where = {"home": "vs", "away": "at", "neutral": "vs"}.get(row["site"], "vs")
        week = row["week"]
        week_txt = f"Preseason W{week[-1]}" if str(week).startswith("PRE") else f"Week {week}"
        detail_bits = [week_txt]
        if row.get("tv"):
            detail_bits.append(row["tv"])
        if row.get("note"):
            detail_bits.append(row["note"])
        # Per-game radio station exactly as 49ers.com lists it (session 2
        # re-verification 2026-09-21); earlier games ran on KSFO 810 AM /
        # KSAN 107.7 FM, later ones on KSAN / KNBR. Never claim a station
        # that the club did not list for that game.
        radio = row.get("radio") or (
            "49ers radio network (KSAN 107.7 FM / KNBR 680 AM & 104.5 FM / KSFO 810 AM during 2026)"
        )
        games.append({
            "league": "NFL",
            "label": f"San Francisco 49ers {where} {row['opponent']}",
            "detail": " - ".join(detail_bits),
            "venue": row.get("venue", ""),
            "priority": "high",
            "source": source,
            "network": radio,
            "date_local": row["date_local"],
            "start_utc": pt_to_utc(row["date_local"], row["kickoff_pt"]),
            "duration": DEFAULT_DURATIONS["NFL"],
            "time_status": "official",
            "tags": ["NFL:49ers"],
        })
    for row in payload["unresolved"]:
        unresolved.append({
            "league": "NFL", "date_local": None,
            "label": f"San Francisco 49ers - week {row['week']}",
            "reason": row["reason"], "source": source,
        })
    return games, unresolved


def from_westwood_one_ncaaf() -> tuple[list[dict], list[dict]]:
    """Westwood One's national NCAA football radio broadcasts (2026 season).

    These are live on KNBR 680 AM / 104.5 FM in San Francisco per the official
    Westwood One Station Finder. Several slots have no published air time and
    are envelope-blocked (NCAAF 11:00-23:59 PT), never guessed.
    """
    payload = load("westwoodone_ncaaf_2026.json")
    source = payload["_meta"]["source"]
    games, unresolved = [], []
    for row in payload["games"]:
        label = row.get("special") or f"{row['away']} at {row['home']}"
        has_time = bool(row.get("air_et"))
        if has_time:
            # Westwood One publishes Eastern air time (includes pre-game).
            start_utc = et_to_utc(row["date_local"], row["air_et"])
            status = "published_air_time"
            duration = DEFAULT_DURATIONS["NCAAF"]
        else:
            start_utc = pt_to_utc(row["date_local"], TBD_ENVELOPE["NCAAF"][0])
            status = "TBD_envelope"
            duration = _envelope_minutes("NCAAF")
        games.append({
            "league": "NCAAF",
            "label": label,
            "detail": "Westwood One national radio" + ("" if has_time else " (air time TBD)"),
            "venue": row.get("venue", ""),
            "priority": "normal",
            "source": row.get("event_url") or source,
            "network": "Westwood One Sports (SF affiliate: KNBR 680 AM / 104.5 FM)",
            "date_local": row["date_local"],
            "start_utc": start_utc,
            "duration": duration,
            "time_status": status,
            "tags": ["NCAAF:national"],
        })
        if not has_time:
            unresolved.append({
                "league": "NCAAF", "date_local": row["date_local"],
                "label": label,
                "reason": "Westwood One has confirmed the game date but not its air time; blocked via the NCAAF TBD envelope.",
                "source": row.get("event_url", source),
            })
    return games, unresolved


def from_ncaaf() -> tuple[list[dict], list[dict]]:
    payload = load("bay_area_2026.json")["ncaaf"]
    source = payload["source"][0]
    games, unresolved, seen = [], [], set()
    for row in payload["games"]:
        opponent = row["opponent"]
        # The Big Game is listed twice (once per school). Keep one interval.
        key = (row["date_local"], tuple(sorted((row["team"], opponent))))
        if key in seen or (
            row["date_local"], tuple(sorted((opponent, row["team"])))
        ) in seen:
            continue
        seen.add(key)
        label = f"{row['team']} vs {opponent}" if row["site"] != "away" else f"{row['team']} at {opponent}"
        kickoff = row.get("kickoff_pt")
        if kickoff:
            start_utc = pt_to_utc(row["date_local"], kickoff)
            status = row.get("time_status", "official")
        else:
            start_utc = pt_to_utc(row["date_local"], TBD_ENVELOPE["NCAAF"][0])
            status = "TBD_envelope"
        games.append({
            "league": "NCAAF",
            "label": label,
            "detail": row.get("tv", "") or "kickoff time not announced",
            "venue": row.get("venue", ""),
            "priority": "high",
            "source": source,
            "network": "KNBR 680 AM / 104.5 FM (radio home of Stanford and Cal)",
            "date_local": row["date_local"],
            "start_utc": start_utc,
            "duration": (
                DEFAULT_DURATIONS["NCAAF"] if kickoff else _envelope_minutes("NCAAF")
            ),
            "time_status": status,
            "tags": ncaaf_tags(row["team"], opponent),
        })
    for row in payload["unresolved"]:
        unresolved.append({
            "league": "NCAAF", "date_local": None,
            "label": "Stanford / California football",
            "reason": row["reason"], "source": source,
        })
    return games, unresolved


def from_mls() -> tuple[list[dict], list[dict]]:
    payload = load("bay_area_2026.json")["mls_earthquakes"]
    source = payload["source"]
    games, unresolved = [], []
    for row in payload["games"]:
        where = "vs" if row["site"] == "home" else "at"
        kickoff = row.get("kickoff_pt")
        games.append({
            "league": "MLS",
            "label": f"San Jose Earthquakes {where} {row['opponent']}",
            "detail": row.get("venue", ""),
            "venue": row.get("venue", ""),
            "priority": "high",
            "source": source,
            "network": "KNBR 680 AM / 104.5 FM (radio home of the Earthquakes)",
            "date_local": row["date_local"],
            "start_utc": pt_to_utc(
                row["date_local"],
                kickoff or TBD_ENVELOPE["MLS"][0],
            ),
            "duration": (
                DEFAULT_DURATIONS["MLS"] if kickoff else _envelope_minutes("MLS")
            ),
            "time_status": "official" if kickoff else "TBD_envelope",
            "tags": ["MLS:Earthquakes"],
        })
    for row in payload["unresolved"]:
        unresolved.append({
            "league": "MLS", "date_local": None,
            "label": "San Jose Earthquakes",
            "reason": row["reason"], "source": source,
        })
    return games, unresolved


def from_other_radio_sports() -> tuple[list[dict], list[dict]]:
    """Warriors (NBA) and Valkyries (WNBA) on KGMZ 95.7, plus research disclosures.

    These answer the request to look for OTHER Bay Area live radio sports and flag
    them high priority. They carry tags that belong to none of the three requested
    sections, so they only count in the `all` scope; Sections 1-3 are unchanged.
    Only AM/FM broadcasts block time. Valkyries rows whose radio column is the
    Audacy app alone are streaming-only and are disclosed, never blocked (the
    user's definition is a standard AM/FM radio in 94122).
    """
    payload = load("other_radio_sports.json")
    games: list[dict] = []
    unresolved: list[dict] = []

    warriors = payload["warriors"]
    w_src = warriors["schedule_sources"][0]
    for row in warriors["games_2026_27"]:
        where = "at" if row["ha"] == "away" else "vs"
        detail = (row.get("phase", "regular") + " · tip-off per published schedule grid (ET)"
                  + (f" · {row['tv']}" if row.get("tv") else ""))
        games.append({
            "league": "NBA",
            "label": f"Golden State Warriors {where} {row['opponent']}",
            "detail": detail,
            "venue": row.get("venue", ""),
            "priority": "high",
            "source": w_src,
            "network": "KGMZ 95.7 The Game (radio flagship; per-game carriage presumed)",
            "date_local": utc_to_local_date(et_to_utc(row["date"], row["start_et"])),
            "start_utc": et_to_utc(row["date"], row["start_et"]),
            "duration": DEFAULT_DURATIONS["NBA"],
            "time_status": "published_start_time",
            "tags": ["NBA:Warriors"],
        })

    valk = payload["valkyries"]
    v_src = valk["radio_sources"][0]
    streaming_only = 0
    for row in valk["games_2026"]:
        if not row.get("on_957"):
            streaming_only += 1
            continue
        where = "at" if row["ha"] == "away" else "vs"
        games.append({
            "league": "WNBA",
            "label": f"Golden State Valkyries {where} {row['opponent']}",
            "detail": (row.get("phase", "regular") + " · tip-off per the club's broadcast table (PT)"
                       + (" · " + row["date_flag"] if row.get("date_flag") else "")),
            "venue": "Chase Center" if row["ha"] == "home" else "",
            "priority": "high",
            "source": v_src,
            "network": "KGMZ 95.7 The Game (club's published radio column)",
            "date_local": row["date"],
            "start_utc": pt_to_utc(row["date"], row["start_pt"]),
            "duration": DEFAULT_DURATIONS["WNBA"],
            "time_status": "published_start_time",
            "tags": ["WNBA:Valkyries"],
        })
        if row.get("date_flag"):
            unresolved.append({
                "league": "WNBA", "date_local": row["date"], "label": row["opponent"],
                "reason": row["date_flag"], "source": v_src,
            })

    playoffs = valk["playoffs_2026"]
    for row in playoffs["reserved_dates"]:
        date_iso = row["date"]
        games.append({
            "league": "WNBA",
            "label": row["label"],
            "detail": "playoff date reserved conservatively; time and opponent "
                      + row["status"].lower() + ". " + playoffs["playoff_radio"],
            "venue": "Chase Center (first home playoff game) / TBD",
            "priority": "high",
            "source": playoffs["sources"][0],
            "network": "presumed KGMZ 95.7 - playoff radio carriage NOT published",
            "date_local": date_iso,
            "start_utc": pt_to_utc(date_iso, TBD_ENVELOPE["WNBA"][0]),
            "duration": _envelope_minutes("WNBA"),
            "time_status": "TBD_envelope",
            "status": row["status"],
            "tags": ["WNBA:Valkyries"],
        })
        unresolved.append({
            "league": "WNBA", "date_local": date_iso, "label": row["label"],
            "reason": f"{row['status']}. Time and opponent not announced; the full date is "
                      "reserved so it can never read as free. " + playoffs["playoff_radio"],
            "source": playoffs["sources"][0],
        })

    if streaming_only:
        unresolved.append({
            "league": "WNBA", "date_local": None,
            "label": f"Valkyries streaming-only games ({streaming_only} of 2026)",
            "reason": "The club's radio column lists 'The Audacy App' only for these games: "
                      "no AM/FM broadcast, so they are NOT counted busy on a standard radio. "
                      "Rows stay auditable in data/verified/other_radio_sports.json (on_957=false).",
            "source": v_src,
        })
    unresolved.append({
        "league": "WNBA", "date_local": None,
        "label": "Valkyries playoffs beyond the first round",
        "reason": valk["playoffs_2026"]["later_rounds"],
        "source": valk["playoffs_2026"]["sources"][0],
    })
    for item in payload.get("unresolved_coverage", []):
        unresolved.append({
            "league": "NBA", "date_local": None, "label": item["name"],
            "reason": item["finding"], "source": item["sources"][0],
        })
    return games, unresolved


def ncaaf_tags(team: str, opponent: str) -> list[str]:
    """Section tags for a Stanford/Cal football game.

    The 129th Big Game is listed once per school and must carry BOTH tags; the
    ACC Championship Game is only relevant if either school qualifies, so it is
    tagged for both as well (conservative -- it is conditional and the site says so).
    """
    tags = set()
    blob = f"{team} {opponent}".lower()
    if "stanford" in blob or "big game" in blob:
        tags.add("NCAAF:Stanford")
    if "california" in blob or "cal " in blob or "big game" in blob:
        tags.add("NCAAF:California")
    if not tags:
        tags.add("NCAAF:Stanford")
        tags.add("NCAAF:California")
    return sorted(tags)


def from_nfl_calendar() -> tuple[list[dict], list[dict]]:
    """NFL postseason / all-star placeholders, so the day board knows they exist.

    Westwood One carries every NFL playoff game and the Super Bowl nationally, and
    the NFL's own key-dates release fixes the round dates through 2026-27. Without
    these records the day board reported e.g. 2027-01-17 (Wild Card Sunday) as a
    free day whenever the 49ers were not the listed participant -- exactly the class
    of bug this project exists to prevent.

    Every record is a date-level envelope with participants TBA. No kickoff time is
    invented. Rows whose round date is not yet official are labelled ESTIMATED.
    """
    games: list[dict] = []
    unresolved: list[dict] = []
    for season_year in (2026, 2027, 2028, 2029):
        sb_iso, sb_status, sb_note = nfl_calendar.super_bowl_for_season(season_year)
        rounds = nfl_calendar.previous_season_nfl_dates(sb_iso)
        for round_name in ("Wild Card", "Divisional", "Conference Championships", "Super Bowl"):
            for date_iso in rounds[round_name]:
                if int(date_iso[:4]) != season_year + 1 and round_name != "Super Bowl":
                    continue
                verified = sb_status == "VERIFIED" and season_year == 2026
                label = {
                    "Wild Card": "NFL Wild Card playoff game (TBA)",
                    "Divisional": "NFL Divisional playoff game (TBA)",
                    "Conference Championships": "NFL Conference Championship (TBA)",
                    "Super Bowl": f"Super Bowl ({sb_note.split(',')[0].strip()})",
                }[round_name]
                games.append({
                    "league": "NFL",
                    "label": label,
                    "detail": f"{round_name} round of the {season_year} season"
                              + ("" if verified else " - round date ESTIMATED, not yet released by the NFL"),
                    "venue": "",
                    "priority": "high" if round_name in ("Conference Championships", "Super Bowl") else "normal",
                    "source": "https://www.seahawks.com/news/nfl-announces-important-dates-for-2026-2027"
                              if verified else "NOT RELEASED - derived from the verified 2026-27 template",
                    "network": "Westwood One Sports (national radio) - verified San Francisco affiliates: KNBR 680 AM / 104.5 FM / KTCT 1050 AM",
                    "date_local": date_iso,
                    "start_utc": pt_to_utc(date_iso, TBD_ENVELOPE["NFL"][0]),
                    "duration": _envelope_minutes("NFL"),
                    "time_status": "TBD_envelope",
                    "status": "VERIFIED" if verified else "ESTIMATED",
                    "tags": ["NFL:national"],
                })
                unresolved.append({
                    "league": "NFL",
                    "date_local": date_iso,
                    "label": label,
                    "reason": f"Round date is {'official' if verified else 'ESTIMATED (NFL has not released it)'}; "
                              "participants and kickoff time are not determined. "
                              "Westwood One carries every NFL playoff game nationally, so the date is busy regardless of which clubs qualify.",
                    "source": f"https://www.nfl.com/schedules/ (Super Bowl anchor {sb_iso}, {sb_status})",
                })
        # Pro Bowl Games (NFL all-star).
        pb_iso, pb_status, pb_note = nfl_calendar.PRO_BOWL_BY_YEAR[season_year + 1]
        games.append({
            "league": "NFL",
            "label": "NFL Pro Bowl Games (all-star)",
            "detail": pb_note,
            "venue": "",
            "priority": "normal",
            "source": "https://operations.nfl.com/updates/the-game/2026-pro-bowl-games-presented-by-verizon-moved-to-tuesday-of-super-bowl-lx-week-in-bay-area/"
                      if pb_status == "VERIFIED" else "NOT RELEASED - Tuesday-of-Super-Bowl-week pattern",
            "network": "",
            "date_local": pb_iso,
            "start_utc": pt_to_utc(pb_iso, TBD_ENVELOPE["NFL"][0]),
            "duration": _envelope_minutes("NFL"),
            "time_status": "TBD_envelope",
            "status": pb_status,
            "tags": ["NFL:national"],
        })
        unresolved.append({
            "league": "NFL",
            "date_local": pb_iso,
            "label": "NFL Pro Bowl Games (all-star)",
            "reason": f"{pb_status}: {pb_note}",
            "source": "https://operations.nfl.com/updates/the-game/2026-pro-bowl-games-presented-by-verizon-moved-to-tuesday-of-super-bowl-lx-week-in-bay-area/",
        })
    games.sort(key=lambda g: g["date_local"])
    return games, unresolved


def from_nfl_schedule_radio_backstop(
    existing: list[dict], schedule: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Block an NFL date conservatively when the full 2026 slate is known.

    The full league schedule answers *which games are scheduled*, but it does not
    say which one Westwood One will select for the Bay Area affiliate.  The
    selection itself remains the radio source of truth.  On a date with no
    published selection we therefore retain one clearly labelled, date-level
    envelope backed by the official full-slate source.  This replaces the old
    generic ``national radio window TBA`` season-frame row for 2026; it never
    invents a matchup or kickoff.
    """
    covered = {
        g.get("date_local") for g in existing
        if g.get("league") == "NFL" and g.get("date_local")
    }
    by_date: dict[str, list[dict]] = {}
    for row in schedule:
        dates = [row["date_local"]] if row.get("date_local") else (row.get("date_window") or [])
        for date_iso in dates:
            by_date.setdefault(date_iso, []).append(row)

    games, unresolved = [], []
    for date_iso in sorted(by_date):
        if date_iso in covered:
            continue
        rows = by_date[date_iso]
        count = len(rows)
        has_unassigned = any(not row.get("date_local") for row in rows)
        detail = (
            (
                "Official Week 18 matchup set is shown for this date window; the 16 games "
                "are not assigned to Saturday or Sunday yet."
            ) if has_unassigned and any(row.get("week") == 18 for row in rows) else
            (
                f"Official 2026 NFL schedule has {count} regular-season game(s) in this "
                "date window; flexible Saturday/Sunday assignment is not published."
            ) if has_unassigned else
            (
                f"Official 2026 NFL schedule has {count} regular-season game(s) on this date; "
                "the Westwood One national selection is not in the bundled radio snapshot. "
                "The full matchup list is shown in the NFL schedule reference."
            )
        )
        games.append({
            "league": "NFL",
            "label": "NFL schedule day - radio selection not published",
            "detail": detail,
            "venue": "",
            "priority": "normal",
            "source": NFL_FULL_SCHEDULE_SOURCE,
            "network": "Westwood One Sports (national NFL radio) - San Francisco affiliate",
            "date_local": date_iso,
            "start_utc": pt_to_utc(date_iso, TBD_ENVELOPE["NFL"][0]),
            "duration": _envelope_minutes("NFL"),
            "time_status": "TBD_envelope",
            "status": "VERIFIED schedule / UNRESOLVED radio selection",
            "schedule_backstop": True,
            "tags": ["NFL:national"],
        })
        unresolved.append({
            "league": "NFL",
            "date_local": date_iso,
            "label": "NFL schedule day - radio selection not published",
            "reason": (
                "The official full NFL schedule confirms games on this date, but the "
                "bundled Westwood One page does not identify the Bay Area national slot. "
                "A conservative envelope prevents a false free day."
            ),
            "source": NFL_FULL_SCHEDULE_SOURCE,
        })
    return games, unresolved


def from_nfl_season_frame(
    existing: list[dict], full_schedule: list[dict] | None = None
) -> tuple[list[dict], list[dict]]:
    """One conservative record per uncovered NFL game date.

    2026 is now covered by the official 272-game schedule plus the explicit radio
    backstop above, so this fallback no longer emits the old generic label for
    2026.  It remains necessary for 2027-2029, whose league schedules are not
    released and therefore cannot be represented as real game rows.
    """
    covered = {
        g["date_local"] for g in existing
        if g.get("league") == "NFL" and g.get("date_local")
    }
    schedule_dates = {
        g.get("date_local") for g in (full_schedule or []) if g.get("date_local")
    }
    games, unresolved = [], []
    for season_year in (2026, 2027, 2028, 2029):
        status = "VERIFIED" if season_year == 2026 else "ESTIMATED"
        for date_iso in nfl_calendar.season_game_dates(season_year):
            if date_iso in covered or (season_year == 2026 and date_iso in schedule_dates):
                continue
            preseason_only = season_year == 2026 and date_iso < "2026-09-09"
            label = (
                "NFL preseason game date - see official preseason schedule"
                if preseason_only else "NFL season date - schedule not released"
            )
            detail = (
                "The official 2026 preseason schedule occupies this date; the full "
                "regular-season bundle begins on 2026-09-09."
                if preseason_only else
                f"{season_year} NFL season shape indicates a game date, but the full league schedule is not released"
            )
            games.append({
                "league": "NFL",
                "label": label,
                "detail": detail,
                "venue": "",
                "priority": "normal",
                "source": NFL_FULL_SCHEDULE_SOURCE if status == "VERIFIED"
                          else "NOT RELEASED - NFL week shape (Sunday/Monday/Thursday) applied to the league calendar",
                "network": "Westwood One Sports (national NFL radio) - SF affiliate",
                "date_local": date_iso,
                "start_utc": pt_to_utc(date_iso, TBD_ENVELOPE["NFL"][0]),
                "duration": _envelope_minutes("NFL"),
                "time_status": "TBD_envelope",
                "status": status,
                "tags": ["NFL:national"],
                "season_frame": not preseason_only,
                "preseason_frame": preseason_only,
                "season_year": season_year,
            })
        if season_year != 2026:
            unresolved.append({
                "league": "NFL", "date_local": None,
                "label": f"{season_year} NFL season - unreleased schedule",
                "reason": (
                    f"{season_year} is not represented by an official full schedule in this bundle. "
                    "Date-level conservative records prevent an NFL Sunday from reading free."
                ),
                "source": "https://www.westwoodonesports.com/nfl-schedule/",
            })
    return games, unresolved

def from_mlb_postseason() -> tuple[list[dict], list[dict]]:
    """The 2026 MLB postseason, using the official per-date list.

    Verified from the MLB Stats API on 2026-09-20. The dates are exact, including
    the five dates that carry no game under any scenario (2026-10-02, 10-21, 10-22,
    10-25, 10-29 are travel days). An earlier revision blocked 2026-09-29 through
    2026-10-31 as one continuous span and therefore over-blocked those five days.

    Times are NOT resolved: every game is served with the 07:33:00Z sentinel. The
    engine blocks each official date with the documented MLB TBD envelope and marks
    the interval `time_confirmed = False`. See docs/IRREGULARITIES.md IR-02.
    """
    payload = load("mlb_postseason_2026.json")
    src = payload["_meta"]["primary_source"]
    clinched = payload["clinch_status"]["clinched_postseason_berth"]
    games, unresolved = [], []
    rounds_by_date: dict[str, str] = {}
    for round_info in payload["rounds"]:
        for date_iso in round_info["dates"]:
            rounds_by_date.setdefault(date_iso, round_info["round"])
    for date_iso in sorted(payload["dates_with_a_reserved_game"]):
        round_name = rounds_by_date[date_iso]
        games.append({
            "league": "MLB",
            "label": f"MLB {round_name} (participants TBD)",
            "detail": f"official {round_name} date; first pitch not published (API sentinel {MLB_TBD_SENTINEL_UTC}Z). "
                      f"Clinched so far: {', '.join(clinched)}.",
            "venue": "",
            "priority": "normal",
            "source": src,
            "network": "MLB league schedule; Bay Area AM/FM carriage unconfirmed",
            "date_local": date_iso,
            "start_utc": f"{date_iso}T{MLB_TBD_SENTINEL_UTC}Z",
            "duration": DEFAULT_DURATIONS["MLB"],
            "time_status": "TBD_official_date",
            "placeholder": True,
            "status": "VERIFIED (date) / UNRESOLVED (time)",
            "tags": ["MLB"],
        })
        unresolved.append({
            "league": "MLB",
            "date_local": date_iso,
            "label": f"MLB {round_name} - first pitch time",
            "reason": "Date is official and machine-confirmed; first pitch time is not published. "
                      "A clinched berth does not establish a matchup or first-pitch time.",
            "source": src,
        })
    return games, unresolved



def _envelope_minutes(league: str) -> int:
    start, end = TBD_ENVELOPE[league]
    def minutes(value):
        h, m = map(int, value.split(":"))
        return h * 60 + m
    return minutes(end) - minutes(start)


# ---------------------------------------------------------------------------
# MLB regular-season occupancy from the official season frame
# ---------------------------------------------------------------------------


def mlb_regular_season_days() -> list[str]:
    """Every date the 2026 MLB regular season is in progress.

    Verified from the MLB Stats API seasons endpoint (2026-03-25 to 2026-09-27).
    MLB plays at least one game on essentially every one of those dates; per-game
    times are fetched live by the app from the same API.
    """
    seasons = load("seasons.json")["mlb"]["2026"]
    start = datetime.strptime(seasons["regular_season_start"], "%Y-%m-%d").date()
    end = datetime.strptime(seasons["regular_season_end"], "%Y-%m-%d").date()
    out = []
    day = start
    while day <= end:
        out.append(day.isoformat())
        day += timedelta(days=1)
    return out


_BUILD_CACHE: dict | None = None


def build(use_cache: bool = True) -> dict:
    """Assemble the bundle. Cached because the test suite calls it repeatedly."""
    global _BUILD_CACHE
    if use_cache and _BUILD_CACHE is not None:
        return _BUILD_CACHE
    result = _build()
    _BUILD_CACHE = result
    return result


def _build() -> dict:
    games: list[dict] = []
    unresolved: list[dict] = load("review_flags.json")
    nfl_schedule_2026 = load_nfl_regular_schedule()
    for loader in (from_westwood_one, from_49ers, from_westwood_one_ncaaf, from_ncaaf, from_mls,
                   from_mlb_postseason, from_nfl_calendar, from_other_radio_sports):
        g, u = loader()
        games.extend(g)
        unresolved.extend(u)

    snapshot_path = VERIFIED / "mlb_schedule_2026.json"
    mlb_snapshot = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else None
    if mlb_snapshot:
        # Replace aggregate postseason rows only on dates with API game records.
        dates = {g["date_local"] for g in mlb_snapshot["games"]}
        games = [g for g in games if not (g["league"] == "MLB" and g["date_local"] in dates)]
        games.extend(mlb_snapshot["games"])
        unresolved = [u for u in unresolved if not (u["league"] == "MLB" and u.get("date_local") in dates)]
        unresolved.extend({"league": "MLB", "date_local": g["date_local"], "label": g["label"],
                           "reason": "Official feed: first pitch TBD; full date reserved.", "source": g["source"]}
                          for g in mlb_snapshot["games"] if g["time_status"] == "TBD_official_date")

    # The league schedule is a reference dataset; only the national-radio
    # backstop is fed into the busy engine.  This keeps a 272-game league slate
    # from being mistaken for 272 simultaneous Bay Area radio broadcasts.
    backstop_games, backstop_unresolved = from_nfl_schedule_radio_backstop(
        games, nfl_schedule_2026
    )
    games.extend(backstop_games)
    unresolved.extend(backstop_unresolved)

    frame_games, frame_unresolved = from_nfl_season_frame(games, nfl_schedule_2026)
    games.extend(frame_games)
    unresolved.extend(frame_unresolved)

    profiles = load_profiles()
    for game in games:
        game["sections"] = sections_for_tags(game.get("tags", []), profiles)

    # Stable ordering: by UTC instant then label.
    games.sort(key=lambda g: (g["start_utc"], g["label"]))

    seasons = json.loads((VERIFIED / "seasons.json").read_text(encoding="utf-8"))
    mlb_frames = {}
    postseason = load("mlb_postseason_2026.json")
    covered = []
    if postseason["dates_with_a_reserved_game"]:
        covered = [[
            "2026-09-28",
            max(postseason["dates_with_a_reserved_game"]),
        ]]
    if mlb_snapshot:
        covered += [["2026-02-20", "2026-09-27"]]
    for year, frame in seasons["mlb"].items():
        mlb_frames[year] = {
            "start": frame["spring_training_start"],
            "end": frame["postseason_end"],
            "status": frame["status"],
            "label": f"{year} MLB season (Spring Training through the postseason)",
            "estimated": frame["status"] != "VERIFIED",
            "source": frame.get("source", ""),
            # Dates inside these ranges have a COMPLETE per-date game list in the
            # bundle, so a date with no game there is genuinely free of MLB and the
            # season-frame envelope must not be applied. 2026 only: the postseason
            # was read date by date from the Stats API.
            "complete_ranges": covered if year == "2026" else [],
        }

    from analyze_vacation import main as analyze_main

    vacation = analyze_main(verbose=False)

    bundle = {
        "_meta": {
            "generated_by": "scripts/build_data.py",
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timezone": "America/Los_Angeles",
            "durations_minutes": DEFAULT_DURATIONS,
            "tbd_envelope_pt": TBD_ENVELOPE,
            "mlb_regular_season_days_2026": {
                "start": "2026-03-25",
                "end": "2026-09-27",
                "count": len(mlb_regular_season_days()),
                "status": "VERIFIED from statsapi.mlb.com/api/v1/seasons. Per-game times are fetched live by the app.",
            },
            "counts": {
                "games": len(games),
                "unresolved": len(unresolved),
                "nfl_regular_schedule_2026": len(nfl_schedule_2026),
                "by_league": {
                    lg: sum(1 for g in games if g["league"] == lg)
                    for lg in ("MLB", "NFL", "NCAAF", "MLS", "NBA", "WNBA")
                },
                "high_priority": sum(1 for g in games if g["priority"] == "high"),
                "westwood_one_ncaaf": sum(
                    1 for g in games if g.get("network", "").startswith("Westwood One Sports") and g["league"] == "NCAAF"
                ),
                "athletics_note": "Athletics (A's) games are carried on KSTE 650 AM (Sacramento) + KNEW 960 AM (Bay Area), NOT KNBR; see docs/SOURCES.md. A's per-game MLB times are fetched live via statsapi.mlb.com like all MLB clubs.",
            },
        },
        "mlb_snapshot": mlb_snapshot["_meta"] if mlb_snapshot else None,
        "games": games,
        "unresolved": unresolved,
        "nfl_schedule_2026": {
            "status": "VERIFIED matchup/date/time snapshot; flexible Week 16/17 and Week 18 date/kickoff fields remain TBD",
            "season": 2026,
            "expected_games": 272,
            "source": NFL_FULL_SCHEDULE_SOURCE,
            "source_pdf": NFL_FULL_SCHEDULE_PDF,
            "retrieved_utc": "2026-09-20T00:00:00Z",
            "radio_note": "Reference schedule only. Sections 1-3 count the Westwood One radio record/backstop, not every league game as an on-air interval.",
            "games": nfl_schedule_2026,
        },
        "vacation": vacation["results"],
        "vacation_compare": vacation["comparison"],
        "vacation_compare_notes": vacation["comparison_notes"],
        "seasons": seasons,
        "sections": profiles,
        "mlb_frames": mlb_frames,
        "radio": load("radio_stations.json"),
        "other_radio": {
            "summary": load("other_radio_sports.json")["_meta"],
            "excluded_streaming_only": load("other_radio_sports.json")["excluded_streaming_only"],
            "unresolved_coverage": load("other_radio_sports.json")["unresolved_coverage"],
            "warriors_note": load("other_radio_sports.json")["warriors"]["radio"],
            "valkyries_note": load("other_radio_sports.json")["valkyries"]["radio"],
        },
        "mlb_clubs": load("mlb_clubs.json"),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "schedule-data.json").write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
    )
    # A .js twin so the page also works when opened straight off the filesystem,
    # where fetch() of a local .json is blocked by CORS.
    (OUT_DIR / "schedule-data.js").write_text(
        "// Generated by scripts/build_data.py - do not edit by hand.\n"
        "window.SCHEDULE_DATA = "
        + json.dumps(bundle, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    return bundle


if __name__ == "__main__":
    result = build()
    meta = result["_meta"]
    print(f"games: {meta['counts']['games']}")
    print(f"  by league: {meta['counts']['by_league']}")
    print(f"  high priority: {meta['counts']['high_priority']}")
    print(f"unresolved (needs review): {meta['counts']['unresolved']}")
    print(f"wrote {OUT_DIR / 'schedule-data.json'}")
    print(f"wrote {OUT_DIR / 'schedule-data.js'}")
