"""Regression tests for the publication/data-honesty review."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lib_windows import game_to_interval, day_report, local_day_bounds, span_minutes
from analyze_vacation import analyze, mls_spans
from build_data import build, from_49ers, from_westwood_one
from nfl_calendar import SUPER_BOWL_BY_YEAR
from refresh_mlb import normalize, refresh


def fixture(**overrides):
    game = {"gamePk": 123, "gameType": "R", "gameDate": "2026-09-21T02:10:00Z",
            "teams": {"away": {"team": {"id": 133, "name": "Athletics"}},
                      "home": {"team": {"id": 147, "name": "New York Yankees"}}},
            "status": {"detailedState": "Scheduled"}}
    game.update(overrides)
    return {"dates": [{"date": "2026-09-20", "games": [game]}]}


class TestPublicationRevision(unittest.TestCase):
    def test_null_start_with_known_date_reserves_full_day(self):
        game = {"league": "NFL", "date_local": "2026-09-20", "start_utc": None}
        self.assertEqual(game_to_interval(game).minutes, 1440)
        self.assertFalse(day_report([game], "2026-09-20")["is_free_day"])

    def test_unknown_date_cannot_be_placed(self):
        self.assertIsNone(game_to_interval({"league": "NFL", "start_utc": None}))

    def test_tbd_covers_dst_days_without_final_minute_gap(self):
        for date, length in [("2026-03-08", 1380), ("2026-11-01", 1500)]:
            game = {"league": "MLB", "date_local": date, "start_utc": None}
            iv = game_to_interval(game)
            self.assertEqual(iv.minutes, length)
            self.assertEqual(day_report([game], date)["free_minutes"], 0)
            self.assertEqual(span_minutes(*local_day_bounds(date)), length)

    def test_2027_opening_night_is_not_vacation(self):
        mlb = json.loads((ROOT / "data/verified/seasons.json").read_text())["mlb"]
        row = analyze(2027, mlb, False, "1")
        self.assertEqual(row["best"]["end"], "2027-03-23")
        self.assertEqual(row["best"]["days"], 37)

    def test_mls_new_format_does_not_invent_late_february_offseason(self):
        seasons = json.loads((ROOT / "data/verified/seasons.json").read_text())
        for year in (2027, 2028, 2029):
            spans = mls_spans(year, seasons)
            self.assertTrue(any(s["start"] <= f"{year}-02-14" <= s["end"] for s in spans))
            self.assertFalse(any(s["start"] <= f"{year}-01-15" <= s["end"] for s in spans))
            self.assertTrue(all(s["status"] == "ESTIMATED" for s in spans))
            self.assertTrue(all(s["source"].startswith("https://www.mlssoccer.com/") for s in spans))

    def test_2029_super_bowl_exact_date_status_matches_sources(self):
        # NFL announced Super Bowl LXIII for Sunday 2029-02-11 on 2026-03-30
        # (Annual Meeting, Phoenix). The old ESTIMATED label was corrected in the
        # 2026-09-21 line-by-line review once the announcement text was re-read.
        self.assertEqual(SUPER_BOWL_BY_YEAR[2029][0], "2029-02-11")
        self.assertEqual(SUPER_BOWL_BY_YEAR[2029][1], "VERIFIED")
        self.assertIn("2026-03-30", SUPER_BOWL_BY_YEAR[2029][2])
        # The 2030 Super Bowl, by contrast, is still an estimate.
        self.assertEqual(SUPER_BOWL_BY_YEAR[2030][1], "ESTIMATED")

    def test_missing_regular_season_data_not_marked_complete(self):
        frame = build()["mlb_frames"]["2026"]
        if not build().get("mlb_snapshot"):
            self.assertFalse(any(a <= "2026-09-20" <= b for a, b in frame["complete_ranges"]))

    def test_ww1_corrected_airtime_and_end_based_on_kickoff(self):
        games, _ = from_westwood_one()
        game = next(g for g in games if g["date_local"] == "2026-09-21")
        self.assertEqual(game["radio_air_utc"], "2026-09-21T23:00:00Z")
        self.assertEqual(game["priority"], "high")
        self.assertTrue(game.get("kickoff_source") or game["duration"] >= 282)

    def test_49ers_per_game_radio_matches_club_listing(self):
        # Session 2 (2026-09-21): every 49ers game's radio field was re-read
        # off 49ers.com. Weeks 2-3 ran on KSFO 810 AM / KSAN 107.7 FM; from
        # Week 4 the club lists KSAN 107.7 FM / KNBR 104.5 FM / 680 AM; the
        # Melbourne opener lists no per-game station. The builder must not
        # flatten all of these into one blanket claim.
        games, _ = from_49ers()
        by_date = {g["date_local"]: g for g in games}
        self.assertEqual(len(games), 19, "3 preseason + 16 regular season")
        for date in ("2026-09-20", "2026-09-27"):
            self.assertIn("KSFO 810 AM", by_date[date]["network"], date)
            self.assertNotIn("KNBR", by_date[date]["network"], date)
        for date in ("2026-10-04", "2026-10-19", "2026-11-22", "2026-12-17", "2027-01-03"):
            self.assertIn("KNBR 104.5 FM", by_date[date]["network"], date)
            self.assertNotIn("KSFO", by_date[date]["network"], date)
        self.assertIn("no per-game station listed", by_date["2026-09-10"]["network"])
        for pre in ("2026-08-13", "2026-08-20", "2026-08-27"):
            self.assertIn("no per-game station listed", by_date[pre]["network"])

    def test_mlb_athletics_not_assigned_knbr(self):
        game = normalize(fixture(), "https://statsapi.mlb.com/")[0]
        self.assertIn("KNEW", game["network"])
        self.assertNotIn("KNBR", game["network"])
        self.assertEqual(game["priority"], "high")
        self.assertEqual(game["date_local"], "2026-09-20")

    def test_mlb_sentinel_and_missing_timestamp_reserve_official_date(self):
        for raw in (None, "2026-09-20T07:33:00Z"):
            game = normalize(fixture(gameDate=raw, officialDate="2026-09-21"), "https://statsapi.mlb.com/")[0]
            self.assertEqual(game["date_local"], "2026-09-21")
            self.assertEqual(game_to_interval(game).minutes, 1440)

    def test_mlb_duplicate_game_ids_are_deduplicated(self):
        p = fixture()
        p["dates"][0]["games"] *= 2
        self.assertEqual(len(normalize(p, "https://statsapi.mlb.com/")), 1)

    def test_empty_unreleased_feed_is_not_a_complete_snapshot(self):
        with self.assertRaises(ValueError):
            normalize({"dates": []}, "https://statsapi.mlb.com/")

    def test_incomplete_refresh_does_not_overwrite_snapshot(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(fixture()).encode()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "snapshot.json"
            out.write_text("previous snapshot")
            with patch("refresh_mlb.urlopen", return_value=Response()):
                with self.assertRaises(ValueError): refresh(2026, out)
            self.assertEqual(out.read_text(), "previous snapshot")

    def test_cancelled_game_does_not_block_original_time(self):
        game = normalize(fixture(status={"abstractGameCode": "O", "codedGameState": "C"}), "https://statsapi.mlb.com/")[0]
        self.assertIsNone(game_to_interval(game))

    def test_pages_publishes_site_not_repository_root(self):
        text = (ROOT / ".github/workflows/pages.yml").read_text()
        self.assertIn("path: site", text)
        self.assertIn("actions/deploy-pages@v4", text)
        self.assertIn("npm test", text)
        self.assertTrue((ROOT / "site/.nojekyll").exists())
        self.assertTrue((ROOT / ".nojekyll").exists())
        self.assertIn('href="site/"', (ROOT / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
