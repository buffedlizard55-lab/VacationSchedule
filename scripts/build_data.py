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
        })
    for row in payload["unresolved"]:
        unresolved.append({
            "league": "MLS", "date_local": None,
            "label": "San Jose Earthquakes",
            "reason": row["reason"], "source": source,
        })
    return games, unresolved


def from_mlb_postseason() -> tuple[list[dict], list[dict]]:
    """The 2026 MLB postseason as served by the Stats API on 2026-09-20.

    Every game carries the 07:33:00Z sentinel, which is MLB's 'time not yet set'
    marker, and placeholder clubs such as 'AL Wild Card #1'.  We record them so
    the day is known to be occupied, but we never fabricate a first pitch: these
    rows are emitted as unresolved with a date-level block instead.
    """
    games, unresolved = [], []
    rounds = [
        ("Wild Card Series", "2026-09-29", "2026-10-01", 4),
        ("Division Series", "2026-10-03", "2026-10-10", 4),
        ("League Championship Series", "2026-10-11", "2026-10-20", 2),
        ("World Series", "2026-10-23", "2026-10-31", 2),
    ]
    src = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31&gameType=E,S,D,L,F,W"
    for name, start, end, per_day in rounds:
        day = datetime.strptime(start, "%Y-%m-%d").date()
        stop = datetime.strptime(end, "%Y-%m-%d").date()
        while day <= stop:
            iso = day.isoformat()
            # Placeholder rows: date verified, time and teams not.
            games.append({
                "league": "MLB",
                "label": f"MLB {name} (participants TBD)",
                "detail": f"official date, first pitch not yet announced (API sentinel {MLB_TBD_SENTINEL_UTC}Z)",
                "venue": "",
                "priority": "normal",
                "source": src,
                "network": "KNBR 680 AM / 104.5 FM carries Giants postseason; Westwood One carries the national postseason feed",
                "date_local": iso,
                "start_utc": f"{iso}T07:33:00Z",
                "duration": DEFAULT_DURATIONS["MLB"],
                "time_status": "TBD_official_date",
                "placeholder": True,
            })
            unresolved.append({
                "league": "MLB", "date_local": iso,
                "label": f"MLB {name}",
                "reason": "Date is official; first pitch time and participants are not yet set in the MLB Stats API.",
                "source": src,
            })
            day += timedelta(days=1)
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
    for loader in (from_westwood_one, from_49ers, from_westwood_one_ncaaf, from_ncaaf, from_mls, from_mlb_postseason):
        g, u = loader()
        games.extend(g)
        unresolved.extend(u)

    # Stable ordering: by UTC instant then label.
    games.sort(key=lambda g: (g["start_utc"], g["label"]))

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
        "seasons": json.loads((VERIFIED / "seasons.json").read_text(encoding="utf-8")),
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
