"""Unit + regression tests for the free-time engine and the built data bundle.

Run:  python3 -m unittest discover -s tests -v

These tests exist to lock down the specific failure the user reported about the
previous version of this tool: "I checked the site and it says that I have free
time on days when there are football games on."  TestDayLevelRegression is the
guard for that.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib_windows import (  # noqa: E402
    DEFAULT_DURATIONS,
    USER_TZ,
    Interval,
    ValidationError,
    day_report,
    find_gaps,
    free_windows,
    is_tbd_utc,
    local_day_bounds,
    local_wall_clock,
    longest_free_window,
    merge,
    parse_utc,
    span_minutes,
)
from analyze_vacation import analyze, blocked_days_for_year  # noqa: E402
from build_data import build, mlb_regular_season_days  # noqa: E402


def iv(start_iso: str, end_iso: str, label: str = "g", priority: str = "normal") -> Interval:
    return Interval(parse_utc(start_iso), parse_utc(end_iso), label, priority)


class TestTimeHelpers(unittest.TestCase):
    def test_parse_utc_handles_z_suffix(self):
        self.assertEqual(parse_utc("2026-09-20T01:10:00Z"), datetime(2026, 9, 20, 1, 10, tzinfo=timezone.utc))

    def test_parse_utc_rejects_naive(self):
        with self.assertRaises(ValidationError):
            parse_utc("2026-09-20T01:10:00")

    def test_span_minutes_is_dst_safe(self):
        """The core regression: same-tzinfo subtraction ignores UTC offset."""
        a = local_wall_clock("2026-11-01", "00:00")
        b = local_wall_clock("2026-11-02", "00:00")
        self.assertEqual(span_minutes(a, b), 1500.0)  # 25h, not 24h
        naive_trap = (b.astimezone(USER_TZ) - a.astimezone(USER_TZ)).total_seconds() / 60
        self.assertEqual(naive_trap, 1440.0, "confirms the documented pitfall is real")

    def test_mlb_tbd_sentinel_detected(self):
        # The Stats API serves every un-announced 2026 postseason game at 07:33Z.
        self.assertTrue(is_tbd_utc("2026-09-29T07:33:00Z"))
        self.assertFalse(is_tbd_utc("2026-09-29T00:33:00Z"))

    def test_local_day_bounds_respect_dst(self):
        # 2026-11-01 is the US DST fallback day in America/Los_Angeles: 25 hours.
        start, end = local_day_bounds("2026-11-01")
        self.assertEqual((end - start).total_seconds() / 3600, 25.0)
        # A normal day is exactly 24 hours.
        start, end = local_day_bounds("2026-09-20")
        self.assertEqual((end - start).total_seconds() / 3600, 24.0)
        # 2026-03-08 is the spring-forward day: 23 hours.
        start, end = local_day_bounds("2026-03-08")
        self.assertEqual((end - start).total_seconds() / 3600, 23.0)

    def test_day_report_uses_true_dst_day_length(self):
        """Regression: 2026-11-01 is 25 hours long, not 24.

        Datetime subtraction ignores the UTC offset when both operands share the
        same tzinfo object, which silently made DST days read as 24 hours and
        under-counted free time on a Sunday carrying a full NFL slate.
        """
        report = day_report([], "2026-11-01")
        self.assertEqual(report["day_length_minutes"], 1500.0)
        self.assertEqual(report["free_minutes"], 1500.0)
        self.assertTrue(report["is_free_day"])
        spring = day_report([], "2026-03-08")
        self.assertEqual(spring["day_length_minutes"], 1380.0)


class TestMergeAndComplement(unittest.TestCase):
    def test_merge_overlapping(self):
        merged = merge([
            iv("2026-09-20T20:00:00Z", "2026-09-20T23:00:00Z", "a"),
            iv("2026-09-20T22:00:00Z", "2026-09-21T01:00:00Z", "b"),
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].end, parse_utc("2026-09-21T01:00:00Z"))

    def test_merge_promotes_high_priority(self):
        merged = merge([
            iv("2026-09-20T20:00:00Z", "2026-09-20T23:00:00Z", "a", "normal"),
            iv("2026-09-20T22:00:00Z", "2026-09-21T01:00:00Z", "b", "high"),
        ])
        self.assertEqual(merged[0].priority, "high")

    def test_merge_disjoint_stays_split(self):
        merged = merge([
            iv("2026-09-20T17:00:00Z", "2026-09-20T18:00:00Z", "a"),
            iv("2026-09-20T20:00:00Z", "2026-09-20T21:00:00Z", "b"),
        ])
        self.assertEqual(len(merged), 2)

    def test_empty_interval_rejected(self):
        with self.assertRaises(ValidationError):
            iv("2026-09-20T20:00:00Z", "2026-09-20T20:00:00Z")

    def test_user_stated_example_1pm_to_5pm_and_8pm_to_10pm(self):
        """The user's own spec: games 1-5 and 8-10 PM must leave 5-8 PM free."""
        day_start, day_end = local_day_bounds("2026-09-20")
        busy = [
            Interval(
                local_wall_clock("2026-09-20", "13:00"),
                local_wall_clock("2026-09-20", "17:00"),
                "g1",
            ),
            Interval(
                local_wall_clock("2026-09-20", "20:00"),
                local_wall_clock("2026-09-20", "22:00"),
                "g2",
            ),
        ]
        windows = free_windows(day_start, day_end, busy)
        self.assertEqual(len(windows), 3)
        middle = windows[1]
        mid_local = middle.start.astimezone(USER_TZ)
        self.assertEqual(mid_local.hour, 17)
        self.assertEqual(middle.end.astimezone(USER_TZ).hour, 20)
        self.assertEqual(middle.minutes, 180.0)
        self.assertEqual(longest_free_window(windows).minutes, 13 * 60)


class TestDayReport(unittest.TestCase):
    def _games(self):
        return [
            {
                "league": "NFL",
                "label": "49ers vs Cardinals",
                "start_utc": "2026-09-27T20:05:00Z",  # 1:05 PM PDT
                "priority": "high",
                "date_local": "2026-09-27",
            },
            {
                "league": "MLB",
                "label": "Giants at Dodgers",
                "start_utc": "2026-09-27T20:10:00Z",
                "priority": "high",
                "date_local": "2026-09-26",
            },
        ]

    def test_nfl_day_is_not_a_free_day(self):
        report = day_report(self._games(), "2026-09-27")
        self.assertFalse(report["is_free_day"])
        self.assertTrue(report["has_high_priority"])
        self.assertGreater(report["busy_minutes"], 0)

    def test_overnight_game_blocks_two_dates(self):
        # First pitch 2026-09-27T05:00Z = 10:00 PM PDT on Sep 26; a 164-minute
        # game ends 12:44 AM PDT on Sep 27.  Both dates must read as busy.
        games = [{
            "league": "MLB",
            "label": "late West Coast game",
            "start_utc": "2026-09-27T05:00:00Z",
            "priority": "normal",
            "date_local": "2026-09-26",
        }]
        report_d0 = day_report(games, "2026-09-26")
        report_d1 = day_report(games, "2026-09-27")
        self.assertFalse(report_d0["is_free_day"], "start date should be busy")
        self.assertFalse(report_d1["is_free_day"], "spill-over date should be busy")
        # Sep 27 is only busy for the 44 minutes that spill past midnight.
        self.assertEqual(report_d1["busy_minutes"], 44.0)

    def test_tbd_mlb_game_blocks_conservatively(self):
        """The core regression the user reported.

        A Wild Card game whose first pitch has not been announced must NOT make
        2026-09-29 read as a free day. It blocks the conservative MLB envelope
        (15:00-23:59 PT = 539 minutes) and is flagged as unconfirmed.
        """
        games = [{
            "league": "MLB",
            "label": "Wild Card G1",
            "start_utc": "2026-09-29T07:33:00Z",
            "date_local": "2026-09-29",
            "time_status": "TBD_official_date",
        }]
        report = day_report(games, "2026-09-29")
        self.assertFalse(report["is_free_day"], "a TBD game must not yield a free day")
        self.assertTrue(report["has_unconfirmed_times"])
        self.assertEqual(report["busy_minutes"], 539.0)
        self.assertEqual(report["unconfirmed_minutes"], 539.0)
        self.assertEqual(len(report["tbd_unresolved"]), 1)
        # The fabricated 03:33 PT sentinel instant must never surface as a time.
        for window in report["busy_windows"]:
            self.assertNotIn("03:33", window["start_pt"])

    def test_durations_default_to_verified_averages(self):
        games = [{
            "league": "NFL", "label": "x",
            "start_utc": "2026-10-04T20:25:00Z", "date_local": "2026-10-04",
        }]
        report = day_report(games, "2026-10-04")
        self.assertEqual(report["busy_minutes"], DEFAULT_DURATIONS["NFL"])
        self.assertEqual(DEFAULT_DURATIONS["NFL"], 192)
        self.assertEqual(DEFAULT_DURATIONS["MLB"], 164)
        self.assertEqual(DEFAULT_DURATIONS["NCAAF"], 204)
        self.assertEqual(DEFAULT_DURATIONS["MLS"], 120)

    def test_radio_air_time_widens_the_block(self):
        game = {
            "league": "NFL", "label": "49ers at Chargers",
            "start_utc": "2026-12-18T01:15:00Z",      # 5:15 PM PT kickoff
            "radio_air_utc": "2026-12-18T00:30:00Z",  # 4:30 PM PT radio air
            "date_local": "2026-12-17",
        }
        report = day_report([game], "2026-12-17")
        # Block must start at the radio air time, not the kickoff.
        self.assertEqual(report["busy_windows"][0]["start_pt"].split(" ")[-2], "16:30")
        self.assertEqual(report["busy_minutes"], 45 + DEFAULT_DURATIONS["NFL"])


class TestFindGaps(unittest.TestCase):
    def test_basic_gap(self):
        gaps = find_gaps({"2026-01-01", "2026-01-05"}, "2026-01-01", "2026-01-07")
        self.assertEqual(gaps[0]["start"], "2026-01-02")
        self.assertEqual(gaps[0]["days"], 3)

    def test_min_days_filter(self):
        gaps = find_gaps({"2026-01-01", "2026-01-05"}, "2026-01-01", "2026-01-07", min_days=7)
        self.assertEqual(gaps, [])

    def test_sorted_longest_first(self):
        gaps = find_gaps({"2026-01-03", "2026-01-09"}, "2026-01-01", "2026-01-12")
        self.assertGreaterEqual(gaps[0]["days"], gaps[-1]["days"])


class TestDayLevelRegression(unittest.TestCase):
    """Guard against the reported bug: a day with games shown as free."""

    def test_no_game_day_is_reported_free(self):
        """No date carrying any scheduled game may ever be reported as free."""
        bundle = build()
        checked = 0
        for game in bundle["games"]:
            report = day_report(bundle["games"], game["date_local"])
            checked += 1
            self.assertFalse(
                report["is_free_day"],
                f"{game['date_local']} has {game['league']} '{game['label']}' "
                f"but day_report called it free",
            )
        self.assertEqual(checked, len(bundle["games"]))
        self.assertGreater(checked, 100, "expected to check most of the bundle")

    def test_postseason_dates_are_never_free(self):
        """Every official 2026 postseason date must read as occupied."""
        bundle = build()
        placeholders = [g for g in bundle["games"] if g.get("placeholder")]
        self.assertTrue(placeholders)
        for game in placeholders:
            report = day_report(bundle["games"], game["date_local"])
            self.assertFalse(report["is_free_day"], f"{game['date_local']} wrongly free")


class TestVacationAnalysis(unittest.TestCase):
    def setUp(self):
        self.mlb = json.loads(
            (ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8")
        )["mlb"]

    def test_2026_blocked_span_is_continuous_under_strict(self):
        blocked, _ = blocked_days_for_year(2026, self.mlb, count_spring_training=True)
        self.assertIn("2026-02-08", blocked)   # Super Bowl LX
        self.assertNotIn("2026-02-09", blocked)
        self.assertIn("2026-02-20", blocked)   # MLB Spring Training opens
        self.assertIn("2026-12-25", blocked)   # Christmas Day NFL

    def test_verified_2026_window_is_eleven_days(self):
        row = analyze(2026, self.mlb, count_spring_training=True)
        self.assertEqual(row["best"]["days"], 11)
        self.assertEqual(row["best"]["start"], "2026-02-09")
        self.assertEqual(row["best"]["end"], "2026-02-19")

    def test_2027_2029_strict_windows(self):
        expected = {2027: 4, 2028: 5, 2029: 7}
        for year, days in expected.items():
            row = analyze(year, self.mlb, count_spring_training=True)
            self.assertEqual(row["best"]["days"], days, f"year {year}")

    def test_regular_season_interpretation_gives_mult_week_windows(self):
        for year in (2026, 2027, 2028, 2029):
            row = analyze(year, self.mlb, count_spring_training=False)
            self.assertGreaterEqual(row["best"]["days"], 21, f"year {year}")

    def test_2029_is_the_best_strict_future_year(self):
        strict = {
            y: analyze(y, self.mlb, True)["best"]["days"] for y in (2027, 2028, 2029)
        }
        self.assertEqual(max(strict, key=strict.get), 2029)


class TestBuiltBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build()

    def test_mlb_regular_season_day_count(self):
        # 2026-03-25 through 2026-09-27 inclusive.
        self.assertEqual(len(mlb_regular_season_days()), 187)

    def test_every_game_has_provenance(self):
        for game in self.bundle["games"]:
            self.assertTrue(game.get("source"), f"missing source: {game.get('label')}")
            self.assertIn(game["league"], DEFAULT_DURATIONS)
            self.assertTrue(game.get("start_utc"))

    def test_no_fabricated_postseason_times(self):
        placeholders = 0
        for game in self.bundle["games"]:
            if game["league"] == "MLB" and game.get("placeholder"):
                placeholders += 1
                self.assertTrue(
                    game["start_utc"].endswith("T07:33:00Z"),
                    f"postseason row must keep the MLB sentinel, got {game['start_utc']}",
                )
                self.assertEqual(game["time_status"], "TBD_official_date")
        self.assertEqual(placeholders, 30, "expected one placeholder per postseason date")

    def test_high_priority_teams_are_flagged(self):
        labels = " ".join(g["label"] for g in self.bundle["games"] if g["priority"] == "high")
        self.assertIn("San Francisco 49ers", labels)
        self.assertIn("San Jose Earthquakes", labels)
        self.assertIn("Stanford", labels)
        self.assertIn("California", labels)

    def test_big_game_not_double_counted(self):
        big = [
            g for g in self.bundle["games"]
            if g["date_local"] == "2026-11-21" and g["league"] == "NCAAF"
        ]
        self.assertEqual(len(big), 1, "the 129th Big Game should appear once")

    def test_bundle_js_is_loadable(self):
        js = (ROOT / "site" / "data" / "schedule-data.js").read_text(encoding="utf-8")
        self.assertTrue(js.startswith("// Generated by"))
        self.assertIn("window.SCHEDULE_DATA =", js)
        payload = json.loads(js.split("window.SCHEDULE_DATA =", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(payload["_meta"]["counts"]["games"], len(self.bundle["games"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
