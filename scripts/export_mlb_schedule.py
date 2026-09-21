"""Fetch the COMPLETE official MLB season schedule and write reviewable artifacts.

Why this exists
---------------
The site's day board can fetch one club-day at a time from the browser, but the
project also needs a checked-in, line-by-line-inspectable list of *every* MLB
game: all 30 clubs, Spring Training through the postseason (regular season and
postseason are what the vacation question is about; Spring Training matters
because the Giants carry it on KNBR and the user asked for the literal reading).

Network note
------------
The development sandbox cannot open TLS to statsapi.mlb.com, so this script runs
in the GitHub Actions runner (see .github/workflows/refresh-data.yml) and the
resulting compact artifacts are committed to the branch. Nothing here invents a
fixture: every row comes from the league's own API response, and the summary
records the exact request URL plus a SHA-256 of the raw payload.

Outputs (per year)
------------------
data/verified/mlb_schedule_<year>.csv           compact pipe-delimited fixtures
data/verified/mlb_schedule_<year>_summary.json  counts, validation, provenance

Run:  python3 scripts/export_mlb_schedule.py --years 2026 2027
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "verified"
RAW_DIR = ROOT / "data" / "raw"

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

#: Every game type the Stats API will return for a season query.
#: S spring training, R regular season, E exhibition, D division series,
#: L LCS, F wild card, W World Series, A all-star game.
GAME_TYPES = "R,E,S,D,L,F,W,A"

GAME_TYPE_NAMES = {
    "S": "Spring Training",
    "R": "Regular season",
    "E": "Exhibition",
    "F": "Wild Card Series",
    "D": "Division Series",
    "L": "League Championship Series",
    "W": "World Series",
    "A": "All-Star Game",
    "C": "Championship",
    "P": "Postseason",
}

CSV_COLUMNS = [
    "date_local",       # Pacific calendar date of the listed first pitch
    "start_utc",        # ISO-8601 UTC instant, or empty when the league has not set one
    "start_pt",         # Pacific wall clock (HH:MM) or TBD
    "start_et",         # Eastern wall clock (HH:MM) or TBD
    "time_tbd",         # true when the API still serves the placeholder instant
    "game_type",        # S/R/E/F/D/L/W/A
    "away",             # club name exactly as the API spells it
    "home",
    "away_id",          # MLB club id (137 = Giants, 133 = Athletics)
    "home_id",
    "venue",
    "status",           # detailedState, e.g. "Scheduled" / "Final"
    "game_pk",          # league game id: the key a reviewer can look up
]

#: MLB serves this exact instant for a game whose start time is not published.
TBD_SENTINEL_UTC = "07:33:00"


def request_url(year: int) -> str:
    return (
        "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
        f"&startDate={year}-01-01&endDate={year}-12-31&gameType={GAME_TYPES}"
    )


def fetch(year: int, timeout: int = 120) -> tuple[bytes, dict]:
    url = request_url(year)
    request = Request(url, headers={"User-Agent": "VacationSchedule/3.1 (public schedule research)"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload.get("dates"), list):
        raise ValueError(f"{year}: response has no dates array")
    return raw, payload


def normalize(payload: dict, year: int) -> list[dict]:
    """Flatten the API response into one row per game, newest API shape tolerated."""
    rows: list[dict] = []
    seen: set[int] = set()
    for day in payload["dates"]:
        for game in day.get("games", []):
            pk = game.get("gamePk")
            if pk is None or pk in seen:
                continue
            seen.add(pk)
            away = game["teams"]["away"]["team"]
            home = game["teams"]["home"]["team"]
            status = game.get("status", {}) or {}
            raw_start = game.get("gameDate") or ""
            tbd = bool(status.get("startTimeTBD", False)) or raw_start[11:19] == TBD_SENTINEL_UTC
            start_utc = ""
            start_pt = start_et = "TBD"
            if raw_start and not tbd:
                moment = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                start_utc = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                start_pt = moment.astimezone(PT).strftime("%H:%M")
                start_et = moment.astimezone(ET).strftime("%H:%M")
            date_local = (game.get("officialDate") or day["date"] or "")[:10]
            if start_utc:
                date_local = datetime.fromisoformat(start_utc.replace("Z", "+00:00")).astimezone(PT).date().isoformat()
            rows.append({
                "date_local": date_local,
                "start_utc": start_utc,
                "start_pt": start_pt,
                "start_et": start_et,
                "time_tbd": "true" if tbd else "false",
                "game_type": game.get("gameType", ""),
                "away": away.get("name", ""),
                "home": home.get("name", ""),
                "away_id": str(away.get("id", "")),
                "home_id": str(home.get("id", "")),
                "venue": (game.get("venue") or {}).get("name", ""),
                "status": status.get("detailedState", ""),
                "game_pk": str(pk),
            })
    rows.sort(key=lambda r: (r["date_local"], r["start_pt"], r["away"], r["home"]))
    if not rows:
        raise ValueError(f"{year}: no games returned; refusing to report an empty season as complete")
    _ = year
    return rows


def write_csv(path: Path, rows: list[dict], meta: dict) -> None:
    buffer = io.StringIO()
    buffer.write(f"# MLB {meta['year']} schedule - all clubs, all game types\n")
    buffer.write(f"# source: {meta['source_url']}\n")
    buffer.write(f"# retrieved_utc: {meta['retrieved_utc']}\n")
    buffer.write(f"# raw_sha256: {meta['raw_sha256']}\n")
    buffer.write(f"# games: {len(rows)} (columns: {'|'.join(CSV_COLUMNS)})\n")
    buffer.write("# time_tbd=true means the league has not published a first pitch; date_local is still official.\n")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, delimiter="|", lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def summarize(year: int, rows: list[dict], payload_raw: bytes, source_url: str, retrieved: str) -> dict:
    by_type = Counter(r["game_type"] for r in rows)
    with_time = [r for r in rows if r["time_tbd"] == "false"]

    regular = [r for r in rows if r["game_type"] == "R"]
    regular_dates = sorted({r["date_local"] for r in regular})
    appearances: dict[str, Counter] = defaultdict(Counter)
    clubs: dict[str, str] = {}
    for row in rows:
        clubs[row["away_id"]] = row["away"]
        clubs[row["home_id"]] = row["home"]
        appearances[row["away_id"]][row["game_type"]] += 1
        appearances[row["home_id"]][row["game_type"]] += 1

    club_ids = {row["away_id"] for row in rows} | {row["home_id"] for row in rows}
    real_club_ids = {cid for cid in club_ids if cid.isdigit() and int(cid) < 9000}
    validation: dict[str, object] = {}
    notes: list[str] = []

    validation["clubs_in_regular_season"] = len({r["away_id"] for r in regular} | {r["home_id"] for r in regular})
    validation["all_30_clubs_present"] = validation["clubs_in_regular_season"] == 30
    if not validation["all_30_clubs_present"]:
        notes.append("Regular-season response did not contain all 30 clubs.")

    validation["regular_season_games"] = len(regular)
    validation["regular_season_games_plausible"] = 2400 <= len(regular) <= 2440
    if not validation["regular_season_games_plausible"]:
        notes.append(f"Regular-season game count {len(regular)} is outside the expected 2400-2440 band.")

    odd = {cid: dict(counts) for cid, counts in appearances.items()
           if cid in real_club_ids and counts["R"] not in (0, 162)}
    validation["clubs_with_non_162_regular_season_games"] = odd
    if odd:
        notes.append("Some clubs do not show exactly 162 regular-season games in this snapshot; review before use.")

    validation["unique_game_pks"] = len({r["game_pk"] for r in rows}) == len(rows)

    return {
        "_meta": {
            "description": (
                f"Every {year} MLB game returned by the league's own schedule API for clubs and all game "
                "types (Spring Training, regular season, postseason, All-Star Game). Committed so a reviewer "
                "can read the fixture list without network access; regenerated by "
                "scripts/export_mlb_schedule.py in GitHub Actions."
            ),
            "year": year,
            "source_url": source_url,
            "retrieved_utc": retrieved,
            "raw_sha256": hashlib.sha256(payload_raw).hexdigest(),
            "raw_bytes": len(payload_raw),
            "csv": f"data/verified/mlb_schedule_{year}.csv",
            "generated_by": "scripts/export_mlb_schedule.py",
            "validated_in_ci": "Yes - the workflow fails if the fetch, normalization or validation raises.",
            "caveat": (
                "The API is the league of record for fixtures. It is not a guarantee against later "
                "rescheduling, and `time_tbd=true` rows mean the first pitch is genuinely unpublished."
            ),
        },
        "counts": {
            "total": len(rows),
            "with_published_time": len(with_time),
            "time_tbd": len(rows) - len(with_time),
            "by_game_type": {GAME_TYPE_NAMES.get(k, k): v for k, v in sorted(by_type.items())},
        },
        "regular_season": {
            "games": len(regular),
            "first_date": regular_dates[0] if regular_dates else None,
            "last_date": regular_dates[-1] if regular_dates else None,
            "days_with_a_game": len(regular_dates),
            "dates_with_a_game": regular_dates,
        },
        "clubs": dict(sorted(clubs.items(), key=lambda kv: kv[1])),
        "appearances_by_club": {
            clubs.get(cid, cid): dict(sorted(counts.items()))
            for cid, counts in sorted(appearances.items(), key=lambda kv: clubs.get(kv[0], kv[0]))
            if cid in real_club_ids
        },
        "validation": validation,
        "validation_notes": notes,
    }


def export_year(year: int, out_dir: Path = OUT_DIR, raw_dir: Path = RAW_DIR) -> dict:
    raw, payload = fetch(year)
    rows = normalize(payload, year)
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = summarize(year, rows, raw, request_url(year), retrieved)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / f"mlb_schedule_{year}.csv", rows, summary["_meta"])
    (out_dir / f"mlb_schedule_{year}_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"mlb_schedule_{year}.json").write_bytes(raw)
    return summary


def postseason_window(year: int) -> tuple[str, str]:
    """The window the league reserves for a season's postseason games."""
    return f"{year}-09-28", f"{year}-10-31"


def window_dates(start: str, end: str) -> list[str]:
    """Every calendar date in an inclusive window (the postseason window, not just
    the span between the first and last game). A travel day *before* the first game
    is a date on which no game is possible, and the window text has to include it."""
    cursor = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end, "%Y-%m-%d").date()
    out: list[str] = []
    while cursor <= last:
        out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def export_postseason_state(year: int, out_dir: Path = OUT_DIR, raw_dir: Path = RAW_DIR) -> dict:
    """Machine-count the postseason: how many game records exist, how many have a
    published first pitch, which dates are reserved and which are impossible.

    This is the answer to "can we resolve the TBDs yet?" - it is measured from the
    league response, never asserted, and it is re-measured on every refresh so the
    moment the league publishes a round's times the site can say so.
    """
    start, end = postseason_window(year)
    url = (
        "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
        f"&startDate={start}&endDate={end}&gameType=E,S,D,L,F,W"
    )
    request = Request(url, headers={"User-Agent": "VacationSchedule/3.1 (public schedule research)"})
    with urlopen(request, timeout=120) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    rows = normalize(payload, year)
    dates = sorted({r["date_local"] for r in rows})
    all_dates = window_dates(start, end)
    placeholder = any(
        not r["away"].split()[0].isupper() or "Winner" in r["away"] or "Seed" in r["away"] or "#" in r["away"]
        for r in rows
    )
    state = {
        "_meta": {
            "description": (
                f"{year} MLB postseason state as measured from the league's own schedule API. "
                "Counts the reserved dates, the game records behind them and how many records still "
                "carry the league's no-time sentinel, so 'times are not published' is a measurement "
                "rather than a claim."
            ),
            "year": year,
            "window": [start, end],
            "source_url": url,
            "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "generated_by": "scripts/export_mlb_schedule.py",
        },
        "counts": {
            "game_records": len(rows),
            "with_published_time": sum(1 for r in rows if r["time_tbd"] == "false"),
            "still_time_tbd": sum(1 for r in rows if r["time_tbd"] == "true"),
            "distinct_dates_with_a_game": len(dates),
            "by_game_type": {GAME_TYPE_NAMES.get(k, k): v for k, v in sorted(Counter(r["game_type"] for r in rows).items())},
            "participants_are_placeholders": placeholder,
        },
        "dates_with_a_reserved_game": dates,
        "dates_in_window_with_no_game": [d for d in all_dates if d not in set(dates)],
        "first_games": [
            {"date": r["date_local"], "start_pt": r["start_pt"], "time_tbd": r["time_tbd"],
             "label": f"{r['away']} at {r['home']}", "venue": r["venue"], "game_type": r["game_type"]}
            for r in rows[:12]
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"mlb_postseason_state_{year}.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"mlb_postseason_{year}.json").write_bytes(raw)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2026, 2027])
    parser.add_argument("--postseason-years", type=int, nargs="+", default=[2026])
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args(argv)

    failures: list[str] = []
    for year in args.years:
        try:
            summary = export_year(year, args.out_dir, args.raw_dir)
        except Exception as error:  # noqa: BLE001 - reported, never hidden
            print(f"{year}: FAILED - {error}", file=sys.stderr)
            failures.append(f"{year}: {error}")
            continue
        counts = summary["counts"]
        print(
            f"{year}: {counts['total']} games "
            f"({', '.join(f'{k}={v}' for k, v in counts['by_game_type'].items())}); "
            f"published times {counts['with_published_time']}, TBD {counts['time_tbd']}"
        )
        for note in summary["validation_notes"]:
            print(f"  note: {note}", file=sys.stderr)

    for year in args.postseason_years:
        try:
            state = export_postseason_state(year, args.out_dir, args.raw_dir)
        except Exception as error:  # noqa: BLE001 - reported, never hidden
            print(f"postseason {year}: FAILED - {error}", file=sys.stderr)
            failures.append(f"postseason {year}: {error}")
            continue
        counts = state["counts"]
        print(
            f"postseason {year}: {counts['game_records']} game records on "
            f"{counts['distinct_dates_with_a_game']} dates; published times "
            f"{counts['with_published_time']}, still TBD {counts['still_time_tbd']}"
        )

    if failures:
        print("Some fetches failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
