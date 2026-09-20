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



def pt_to_utc(date_local: str, hhmm: str, dst_hint: bool | None = None) -> str:
    """Convert a local-to-user (America/Los_Angeles) wall-clock time to UTC ISO."""
    moment = datetime.strptime(f"{date_local}T{hhmm}:00", "%Y-%m-%dT%H:%M:%S")
    aware = moment.replace(tzinfo=USER_TZ, fold=0)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            "priority": row.get("priority", "normal"),
            "source": row.get("url") or source,
            "network": "Westwood One Sports (national radio)",
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
        games.append({
            "league": "NFL",
            "label": f"San Francisco 49ers {where} {row['opponent']}",
            "detail": " - ".join(detail_bits),
            "venue": row.get("venue", ""),
            "priority": "high",
            "source": source,
            "network": "KSAN 107.7 FM / KNBR 680 AM & 104.5 FM / KSFO 810 AM",
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


def from_nfl_season_frame(existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """One placeholder per NFL game day the bundle does not already cover.

    The three sections name only the 49ers and the Westwood One national feed, so
    without this the day board would report an NFL Sunday as free whenever the
    national window had not been published -- most visibly for 2027-2029, where
    neither the 49ers nor the Westwood One schedule exists yet.

    These records are date-level and say exactly that: the NFL is scheduled to play
    on this date, the national radio window is not announced, and the day is blocked
    with the documented NFL envelope. Nothing about a specific game is invented.
    """
    covered = {g["date_local"] for g in existing if g.get("league") == "NFL"}
    games, unresolved = [], []
    for season_year in (2026, 2027, 2028, 2029):
        status = "VERIFIED" if season_year == 2026 else "ESTIMATED"
        sb_iso, sb_status, _ = nfl_calendar.super_bowl_for_season(season_year)
        for date_iso in nfl_calendar.season_game_dates(season_year):
            if date_iso in covered:
                continue
            games.append({
                "league": "NFL",
                "label": "NFL games scheduled (national radio window TBA)",
                "detail": f"{season_year} NFL season - the NFL plays on this date; the national radio window is not published"
                          + (" (season not released by the NFL)" if status == "ESTIMATED" else ""),
                "venue": "",
                "priority": "normal",
                "source": "https://www.nfl.com/schedules/" if status == "VERIFIED"
                          else "NOT RELEASED - NFL week shape (Sunday/Monday/Thursday) applied to the league calendar",
                "network": "Westwood One Sports (national NFL radio) - SF: KNBR 680 AM / 104.5 FM / KTCT 1050 AM",
                "date_local": date_iso,
                "start_utc": pt_to_utc(date_iso, TBD_ENVELOPE["NFL"][0]),
                "duration": _envelope_minutes("NFL"),
                "time_status": "TBD_envelope",
                "status": status,
                "tags": ["NFL:national"],
                "season_frame": True,
                "season_year": season_year,
            })
        unresolved.append({
            "league": "NFL", "date_local": None,
            "label": f"{season_year} NFL season - national radio window",
            "reason": f"{len([g for g in games if g['status'] == status])} date(s) in the {season_year} NFL season "
                      "have no published Westwood One national window (or no 49ers game). Each is blocked with the "
                      "NFL envelope instead of being called free; the individual dates are on the day board.",
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
            "network": "KNBR 680 AM / 104.5 FM carries Giants baseball; the national radio feed carries the postseason",
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
                      "MLB sets postseason start times once the field is final on 2026-09-27.",
            "source": src,
        })
    return games, unresolved



def _envelope_minutes(league: str) -> int:
    start, end = TBD_ENVELOPE[league]
    a = datetime.strptime(start, "%H:%M")
    b = datetime.strptime(end, "%H:%M")
    return int((b - a).total_seconds() // 60)


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
    unresolved: list[dict] = []
    for loader in (from_westwood_one, from_49ers, from_westwood_one_ncaaf, from_ncaaf, from_mls,
                   from_mlb_postseason, from_nfl_calendar):
        g, u = loader()
        games.extend(g)
        unresolved.extend(u)

    frame_games, frame_unresolved = from_nfl_season_frame(games)
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
            min(postseason["_meta"].get("retrieved_utc", "2026-09-28")[:10], "2026-09-28"),
            max(postseason["dates_with_a_reserved_game"]),
        ]]
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
                "by_league": {
                    lg: sum(1 for g in games if g["league"] == lg)
                    for lg in ("MLB", "NFL", "NCAAF", "MLS")
                },
                "high_priority": sum(1 for g in games if g["priority"] == "high"),
                "westwood_one_ncaaf": sum(
                    1 for g in games if g.get("network", "").startswith("Westwood One Sports") and g["league"] == "NCAAF"
                ),
                "athletics_note": "Athletics (A's) games are carried on KSTE 650 AM (Sacramento) + KNEW 960 AM (Bay Area), NOT KNBR; see docs/SOURCES.md. A's per-game MLB times are fetched live via statsapi.mlb.com like all MLB clubs.",
            },
        },
        "games": games,
        "unresolved": unresolved,
        "vacation": vacation["results"],
        "vacation_compare": vacation["comparison"],
        "vacation_compare_notes": vacation["comparison_notes"],
        "seasons": seasons,
        "sections": profiles,
        "mlb_frames": mlb_frames,
        "radio": load("radio_stations.json"),
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
