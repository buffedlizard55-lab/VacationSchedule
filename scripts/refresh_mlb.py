"""Fetch an all-club MLB snapshot from the official Stats API, atomically.

Used by the daily Pages workflow, not by offline tests. A failed fetch never
replaces the previous snapshot or claims that an empty future schedule is free.
Run: python3 scripts/refresh_mlb.py [--year 2026] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo("America/Los_Angeles")
GAME_TYPES = "R,E,S,D,L,F,W,A"


def normalize(payload: dict, source: str) -> list[dict]:
    if not isinstance(payload.get("dates"), list):
        raise ValueError("MLB response has no dates array")
    games = []
    seen = set()
    for day in payload["dates"]:
        for g in day.get("games", []):
            pk = g["gamePk"]
            if pk in seen:
                continue
            seen.add(pk)
            away, home = g["teams"]["away"]["team"], g["teams"]["home"]["team"]
            status = g.get("status", {})
            raw = g.get("gameDate")
            tbd = not raw or raw[11:19] == "07:33:00" or status.get("startTimeTBD", False)
            local = g.get("officialDate", day["date"]) if tbd else datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(PT).date().isoformat()
            teams = {home["id"], away["id"]}
            outlets = []
            if 137 in teams:
                outlets.append("Giants affiliate: KNBR 680 AM / 104.5 FM")
            if 133 in teams:
                outlets.append("Athletics affiliate: KNEW 960 AM")
            games.append({
                "id": f"mlb-{pk}", "game_pk": pk, "league": "MLB",
                "game_type": g.get("gameType"), "label": f"{away['name']} at {home['name']}",
                "team_ids": sorted(teams), "date_local": local,
                "start_utc": raw if not tbd else f"{local}T07:33:00Z",
                "time_status": "TBD_official_date" if tbd else "official",
                "duration": 164, "priority": "high" if teams & {133, 137} else "normal",
                "source": source, "tags": ["MLB"], "sections": ["1", "2", "3"],
                "network": "; ".join(outlets) or "Local AM/FM carriage unconfirmed; counts by all-MLB rule",
                "detail": status.get("detailedState", "Scheduled") + " · affiliate affiliation is not per-game carriage confirmation",
                "status": "Official MLB feed · end time estimated",
                "cancelled": status.get("codedGameState") in ("C", "D"),
            })
    # An empty response is not evidence of a released, complete future schedule.
    if not games:
        raise ValueError("No games returned; refusing to mark an unreleased schedule complete")
    return games


def refresh(year: int, output: Path) -> dict:
    source = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={year}-01-01&endDate={year}-12-31&gameType={GAME_TYPES}"
    request = Request(source, headers={"User-Agent": "VacationSchedule/3.0 (public schedule research)"})
    with urlopen(request, timeout=90) as response:
        payload = json.load(response)
    games = normalize(payload, source)
    clubs = {t for g in games if g["game_type"] == "R" for t in g["team_ids"]}
    if len(clubs) != 30 or sum(g["game_type"] == "R" for g in games) < 2400:
        raise ValueError("Incomplete regular-season response: require all 30 clubs and at least 2400 records")
    data = {"_meta": {"source": source, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                      "year": year, "coverage": "All-club API response, not a guarantee against future rescheduling",
                      "complete_ranges": [[f"{year}-02-20", f"{year}-09-27"]] if year == 2026 else []}, "games": games}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    temporary.replace(output)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "verified" / "mlb_schedule_2026.json")
    args = parser.parse_args()
    result = refresh(args.year, args.output)
    print(f"Saved {len(result['games'])} official MLB records to {args.output}")
