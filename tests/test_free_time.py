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
from analyze_vacation import NFL_SEASON_START, analyze, blocked_days_for_year  # noqa: E402
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

    def test_2026_blocked_set_marks_nfl_and_mlb_boundaries(self):
        blocked, _ = blocked_days_for_year(2026, self.mlb, count_spring_training=True)
        self.assertIn("2026-02-08", blocked)     # Super Bowl LX
        self.assertNotIn("2026-02-09", blocked)  # day after the Super Bowl
        self.assertIn("2026-02-20", blocked)     # MLB Spring Training opens
        self.assertIn("2026-12-25", blocked)     # Christmas Day NFL
        self.assertIn("2026-02-03", blocked)     # 2026 Pro Bowl Games (NFL all-star)

    def test_previous_season_playoff_dates_are_verified_against_2026_27(self):
        """The day-of-week template must reproduce the NFL's official 2026-27
        key dates (seahawks.com release, 2026-07-07)."""
        from analyze_vacation import previous_season_nfl_dates
        dates = previous_season_nfl_dates("2027-02-14")
        self.assertEqual(dates["Week 18"], ["2027-01-09", "2027-01-10"])
        self.assertEqual(dates["Wild Card"], ["2027-01-16", "2027-01-17", "2027-01-18"])
        self.assertEqual(dates["Divisional"], ["2027-01-23", "2027-01-24"])
        self.assertEqual(dates["Conference Championships"], ["2027-01-31"])
        self.assertEqual(dates["Super Bowl"], ["2027-02-14"])

    def test_pro_bowl_blocks_super_bowl_week(self):
        blocked, _ = blocked_days_for_year(2027, self.mlb, count_spring_training=True)
        self.assertIn("2027-02-09", blocked)  # Pro Bowl Games (Tuesday of SB week)
        self.assertIn("2027-02-14", blocked)  # Super Bowl LXI

    def test_verified_2026_window_is_eleven_days(self):
        row = analyze(2026, self.mlb, count_spring_training=True)
        self.assertEqual(row["best"]["days"], 11)
        self.assertEqual(row["best"]["start"], "2026-02-09")
        self.assertEqual(row["best"]["end"], "2026-02-19")

    def test_2027_2029_strict_windows(self):
        """With precise NFL dates (not the old continuous Jan->SB span) each
        future year has an 8-day clean run between the conference championships
        and the Pro Bowl Games. No year reaches a full two weeks under strict."""
        expected = {2027: 8, 2028: 8, 2029: 8}
        for year, days in expected.items():
            row = analyze(year, self.mlb, count_spring_training=True)
            self.assertEqual(row["best"]["days"], days, f"year {year}")

    def test_no_strict_year_reaches_two_full_weeks(self):
        for year in (2026, 2027, 2028, 2029):
            row = analyze(year, self.mlb, count_spring_training=True)
            self.assertLess(row["best"]["days"], 14, f"year {year}")

    def test_regular_season_interpretation_gives_mult_week_windows(self):
        for year in (2026, 2027, 2028, 2029):
            row = analyze(year, self.mlb, count_spring_training=False)
            self.assertGreaterEqual(row["best"]["days"], 21, f"year {year}")

    def test_2027_is_verified_and_2028_2029_estimated(self):
        self.assertEqual(self.mlb["2027"]["status"], "VERIFIED")
        self.assertNotEqual(self.mlb["2028"]["status"], "VERIFIED")
        self.assertNotEqual(self.mlb["2029"]["status"], "VERIFIED")


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
        payload = json.loads(
            (ROOT / "data" / "verified" / "mlb_postseason_2026.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            placeholders, len(payload["dates_with_a_reserved_game"]),
            "expected exactly one placeholder per officially reserved postseason date",
        )

    def test_high_priority_teams_are_flagged(self):
        labels = " ".join(g["label"] for g in self.bundle["games"] if g["priority"] == "high")
        self.assertIn("San Francisco 49ers", labels)
        self.assertIn("San Jose Earthquakes", labels)
        self.assertIn("Stanford", labels)
        self.assertIn("California", labels)

    def test_big_game_not_double_counted(self):
        big = [
            g for g in self.bundle["games"]
            if g["date_local"] == "2026-11-21"
            and g["league"] == "NCAAF"
            and "Stanford" in g["label"] and "California" in g["label"]
        ]
        self.assertEqual(len(big), 1, "the 129th Big Game should appear once")
        # Other NCAAF broadcasts (e.g. Westwood One LSU@Tennessee) may share the
        # date legitimately and are not the Big Game.

    def test_bundle_js_is_loadable(self):
        js = (ROOT / "site" / "data" / "schedule-data.js").read_text(encoding="utf-8")
        self.assertTrue(js.startswith("// Generated by"))
        self.assertIn("window.SCHEDULE_DATA =", js)
        payload = json.loads(js.split("window.SCHEDULE_DATA =", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(payload["_meta"]["counts"]["games"], len(self.bundle["games"]))


class TestNflFullSchedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build()
        cls.schedule = cls.bundle["nfl_schedule_2026"]

    def test_official_schedule_has_272_games_and_all_weeks(self):
        games = self.schedule["games"]
        self.assertEqual(len(games), 272)
        self.assertEqual({g["week"] for g in games}, set(range(1, 19)))
        self.assertEqual(self.schedule["expected_games"], 272)
        self.assertIn("nfl.com", self.schedule["source"])
        appearances = {}
        for game in games:
            for team in (game["away_abbr"], game["home_abbr"]):
                appearances[team] = appearances.get(team, 0) + 1
        self.assertEqual(set(appearances.values()), {17})
        self.assertEqual(len(appearances), 32)

    def test_schedule_has_no_shape_only_2026_frame_rows(self):
        self.assertFalse(
            any(g.get("season_frame") and g.get("season_year") == 2026
                for g in self.bundle["games"]),
            "2026 regular-season dates must come from the official slate/backstop",
        )
        self.assertFalse(any("national radio window TBA" in g["label"]
                             for g in self.bundle["games"]))

    def test_flexible_and_week_18_games_stay_unresolved(self):
        games = self.schedule["games"]
        tbd = [g for g in games if g["time_status"] == "TBD_official_window"]
        self.assertEqual(len(tbd), 24)
        self.assertTrue(all(g["date_local"] is None and g["kickoff_et"] is None for g in tbd))
        self.assertTrue(all(len(g["date_window"]) == 2 for g in tbd))
        self.assertEqual({g["week"] for g in tbd}, {16, 17, 18})

    def test_radio_backstop_is_not_a_matchup_claim(self):
        backstops = [g for g in self.bundle["games"] if g.get("schedule_backstop")]
        self.assertTrue(backstops)
        self.assertTrue(all("selection" in g["label"] for g in backstops))
        self.assertTrue(all(g["time_status"] == "TBD_envelope" for g in backstops))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCoverageSections(unittest.TestCase):
    """The three sections the user asked to compare must be exactly what he wrote.

    These tests exist so that a future edit cannot quietly widen or narrow a
    section: the definitions are asserted verbatim against the request.
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = build()
        cls.profiles = json.loads(
            (ROOT / "data" / "verified" / "profiles.json").read_text(encoding="utf-8")
        )

    def test_three_sections_plus_superset(self):
        ids = [s["id"] for s in self.profiles["sections"]]
        self.assertEqual(ids, ["1", "2", "3"])
        self.assertEqual(self.profiles["extra_scope"]["id"], "all")

    def test_section_definitions_match_the_request(self):
        by_id = {s["id"]: s for s in self.profiles["sections"]}
        self.assertEqual(by_id["1"]["definition"], [
            "MLB (Giants and A's flagged high priority; all 30 clubs shown)",
            "NFL - San Francisco 49ers, preseason and regular season and postseason (high priority)",
            "Westwood One Sports national NFL radio broadcasts",
        ])
        self.assertEqual(by_id["2"]["definition"], [
            "MLB (Giants and A's flagged high priority; all 30 clubs shown)",
            "NFL - San Francisco 49ers, preseason and regular season and postseason (high priority)",
            "Stanford NCAAF, California NCAAF (high priority)",
            "Westwood One Sports national NFL radio broadcasts",
        ])
        self.assertEqual(by_id["3"]["definition"], [
            "MLB (Giants and A's flagged high priority; all 30 clubs shown)",
            "NFL - San Francisco 49ers, preseason and regular season and postseason (high priority)",
            "Stanford NCAAF, California NCAAF (high priority)",
            "San Jose Earthquakes MLS (high priority)",
            "Westwood One Sports national NFL radio broadcasts",
        ])

    def test_every_game_carries_a_sections_list(self):
        for game in self.bundle["games"]:
            self.assertIsInstance(game.get("sections"), list, game.get("label"))

    def test_tagging_is_what_the_request_implies(self):
        def sections_for(pred):
            out = set()
            for g in self.bundle["games"]:
                if pred(g):
                    out.update(g["sections"])
            return out

        mlb = sections_for(lambda g: g["league"] == "MLB")
        niners = sections_for(lambda g: "NFL:49ers" in (g.get("tags") or []))
        ww_nfl = sections_for(lambda g: g["league"] == "NFL" and "NFL:national" in (g.get("tags") or []))
        college_bay = sections_for(lambda g: (g.get("tags") or [])[:1] == ["NCAAF:California"]
                                   or (g.get("tags") or [])[:1] == ["NCAAF:Stanford"])
        college_national = sections_for(lambda g: "NCAAF:national" in (g.get("tags") or []))
        mls = sections_for(lambda g: "MLS:Earthquakes" in (g.get("tags") or []))

        self.assertEqual(mlb, {"1", "2", "3"})
        self.assertEqual(niners, {"1", "2", "3"})
        self.assertEqual(ww_nfl, {"1", "2", "3"})
        self.assertEqual(mls, {"3"})
        self.assertTrue(college_bay <= {"2", "3"} and college_bay, "Bay Area college football is section 2+")
        self.assertFalse(college_bay & {"1"}, "Stanford/Cal must not be in section 1")
        self.assertEqual(
            college_national, set(),
            "Westwood One national NCAA football is tracked but is NOT in any of the three sections",
        )

    def test_a_game_outside_the_section_is_not_counted(self):
        """2026-08-29 has Stanford + an Earthquakes match but no MLB/NFL game data."""
        date = "2026-08-29"
        s1 = day_report(self.bundle["games"], date, scope="1")
        s3 = day_report(self.bundle["games"], date, scope="3")
        self.assertNotIn("NCAAF", [w["league"] for w in s1["busy_windows"]])
        self.assertIn("NCAAF", [w["league"] for w in s3["busy_windows"]])
        self.assertGreater(s1["free_minutes"], s3["free_minutes"])

    def test_section_filter_is_monotonic(self):
        for date in ("2026-08-29", "2026-10-03", "2026-11-21", "2027-01-17"):
            free = [day_report(self.bundle["games"], date, scope=s)["free_minutes"] for s in ("1", "2", "3", "all")]
            self.assertGreaterEqual(free[0], free[1], date)
            self.assertGreaterEqual(free[1], free[2], date)


class TestMlbSeasonFrameFallback(unittest.TestCase):
    """When only the season frame is known, the day must not be called free."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = build()
        cls.frames = cls.bundle["mlb_frames"]

    def test_in_season_date_without_per_game_data_is_blocked(self):
        date = "2026-03-01"  # Spring Training, no bundled game
        with_frames = day_report(self.bundle["games"], date, scope="1", mlb_frames=self.frames)
        without = day_report(self.bundle["games"], date, scope="1")
        self.assertTrue(with_frames["is_free_day"] is False)
        self.assertTrue(with_frames["mlb_frame_fallback"])
        self.assertTrue(without["is_free_day"], "the fallback is what prevents the free reading")
        self.assertEqual(with_frames["busy_minutes"], 539.0)  # 15:00 -> 23:59 PT

    def test_verified_postseason_off_day_stays_free(self):
        """2026-10-02 is inside the frame but the bundle's list is complete, and empty."""
        date = "2026-10-02"
        report = day_report(self.bundle["games"], date, scope="1", mlb_frames=self.frames)
        self.assertTrue(report["is_free_day"], "no game is possible on this date")
        self.assertFalse(report["mlb_frame_fallback"])

    def test_frame_never_calls_a_dated_game_free(self):
        for game in self.bundle["games"]:
            if game["league"] != "MLB":
                continue
            report = day_report(self.bundle["games"], game["date_local"], scope="1", mlb_frames=self.frames)
            self.assertFalse(report["is_free_day"], game["date_local"])

    def test_estimated_frames_are_labelled(self):
        self.assertFalse(self.frames["2026"]["estimated"])
        self.assertFalse(self.frames["2027"]["estimated"])
        self.assertTrue(self.frames["2028"]["estimated"])
        self.assertTrue(self.frames["2029"]["estimated"])


class TestPostseason2026(unittest.TestCase):
    """The 2026 postseason must come from the official per-date list, not a span."""

    @classmethod
    def setUpClass(cls):
        cls.bundle = build()
        cls.payload = json.loads(
            (ROOT / "data" / "verified" / "mlb_postseason_2026.json").read_text(encoding="utf-8")
        )

    def test_official_dates_are_the_ones_in_the_bundle(self):
        bundled = {g["date_local"] for g in self.bundle["games"]
                   if g["league"] == "MLB" and g.get("time_status") == "TBD_official_date"}
        self.assertEqual(bundled, set(self.payload["dates_with_a_reserved_game"]))

    def test_travel_days_are_not_blocked(self):
        """An earlier revision blocked 09-29..10-31 continuously and hid these five days."""
        for date in self.payload["off_days_with_no_possible_game"]:
            mlb_games = [g for g in self.bundle["games"]
                         if g["league"] == "MLB" and g["date_local"] == date]
            self.assertEqual(mlb_games, [], f"{date} should carry no MLB game")

    def test_first_pitch_times_are_never_invented(self):
        for game in self.bundle["games"]:
            if game["league"] == "MLB" and game.get("placeholder"):
                self.assertTrue(game["start_utc"].endswith("T07:33:00Z"), game["date_local"])
                self.assertFalse(game.get("time_confirmed", False))

    def test_clinched_clubs_are_recorded_with_a_source(self):
        self.assertGreaterEqual(len(self.payload["clinch_status"]["clinched_postseason_berth"]), 5)
        self.assertIn("mlb.com", self.payload["clinch_status"]["source"])

    def test_postseason_placeholders_never_name_an_unqualified_club(self):
        for game in self.bundle["games"]:
            if game["league"] == "MLB" and game.get("placeholder"):
                self.assertIn("TBD", game["label"], game["label"])


class TestWeekWindowInvariant(unittest.TestCase):
    """No 7-day run can exist inside a season that plays every weekend.

    This is what makes the conservative NFL/MLS/college spans safe: they cannot
    hide a week-long window, because a week always contains a Sunday.
    """

    @classmethod
    def setUpClass(cls):
        cls.mlb = json.loads(
            (ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8")
        )["mlb"]

    def test_no_week_long_run_inside_the_nfl_season(self):
        for section in ("1", "2", "3"):
            for year in (2026, 2027, 2028, 2029):
                hall_of_fame, _, _ = NFL_SEASON_START[year]
                for interpretation in (True, False):
                    row = analyze(year, self.mlb, count_spring_training=interpretation, section=section)
                    for gap in row["gaps"]:
                        if gap["days"] >= 7:
                            self.assertLess(
                                gap["end"], hall_of_fame,
                                f"{year} section {section} strict={interpretation}: "
                                f"{gap['start']}..{gap['end']} runs into the NFL season",
                            )

    def test_requirements_are_consistent_with_days(self):
        for section in ("1", "2", "3"):
            for year in (2026, 2027, 2028, 2029):
                row = analyze(year, self.mlb, count_spring_training=True, section=section)
                req = row["requirements"]
                self.assertEqual(req["weeks_3"], req["weeks_2"] and req["week_1"])
                for gap in row["gaps"]:
                    self.assertEqual(gap["weeks_2"], gap["days"] >= 14)
                    self.assertEqual(gap["weeks_3"], gap["days"] >= 21)

    def test_sections_1_and_2_have_the_same_longest_run(self):
        for year in (2026, 2027, 2028, 2029):
            for interpretation in (True, False):
                a = analyze(year, self.mlb, interpretation, "1")["best"]["days"]
                b = analyze(year, self.mlb, interpretation, "2")["best"]["days"]
                self.assertEqual(a, b, f"{year} strict={interpretation}")


class TestNflSeasonFrame(unittest.TestCase):
    """Every NFL game day must carry a record, even when the project has no
    per-game data for it.

    Sections 1-3 name the 49ers and the Westwood One national feed, not all 272 NFL
    games. Before this layer existed, a Sunday where the 49ers were on bye and the
    national window had not been published read as a FREE day. See IR-29.
    """

    @classmethod
    def setUpClass(cls):
        import nfl_calendar
        cls.cal = nfl_calendar
        cls.bundle = build()

    def test_every_nfl_game_date_has_a_record(self):
        for season_year in (2026, 2027, 2028, 2029):
            for date_iso in self.cal.season_game_dates(season_year):
                game = next(
                    (g for g in self.bundle["games"]
                     if g["league"] == "NFL" and g["date_local"] == date_iso),
                    None,
                )
                self.assertIsNotNone(
                    game, f"{date_iso} is an NFL game day with no record in the bundle")

    def test_no_nfl_sunday_reads_free(self):
        """The reported failure mode, asserted directly for all four seasons."""
        for season_year in (2026, 2027, 2028, 2029):
            for date_iso in self.cal.season_game_dates(season_year):
                rep = day_report(self.bundle["games"], date_iso, scope="1",
                                 mlb_frames=self.bundle["mlb_frames"])
                self.assertFalse(
                    rep["is_free_day"], f"{date_iso} (NFL {season_year} season) reads FREE")

    def test_playoff_rounds_are_recorded_for_every_season(self):
        for season_year in (2026, 2027, 2028, 2029):
            sb_iso, _, _ = self.cal.super_bowl_for_season(season_year)
            rounds = self.cal.previous_season_nfl_dates(sb_iso)
            self.assertTrue(rounds, f"{season_year}: no playoff rounds derived")
            for round_name, dates in rounds.items():
                for date_iso in dates:
                    self.assertTrue(
                        any(g["league"] == "NFL" and g["date_local"] == date_iso
                            for g in self.bundle["games"]),
                        f"{season_year} {round_name} on {date_iso} has no record",
                    )

    def test_placeholders_never_name_a_team(self):
        """A date-level placeholder must not imply a specific matchup."""
        teams = ("49ers", "Giants", "Athletics", "A's", "Stanford", "California",
                 "Earthquakes", "Rams", "Seahawks", "Patriots", "Eagles")
        for game in self.bundle["games"]:
            if not game.get("season_frame"):
                continue
            for team in teams:
                self.assertNotIn(
                    team, game["label"],
                    f"{game['date_local']}: season-frame placeholder names a team",
                )
            self.assertEqual(game["time_status"], "TBD_envelope")
            # An un-timed day must be reported as unconfirmed, not silently certain.
            rep = day_report(self.bundle["games"], game["date_local"])
            self.assertTrue(rep["has_unconfirmed_times"], game["date_local"])

    def test_estimated_seasons_are_labelled_and_have_no_fake_url(self):
        for game in self.bundle["games"]:
            if not game.get("season_frame"):
                continue
            year = game["season_year"]
            if year == 2026:
                self.assertEqual(game["status"], "VERIFIED")
                self.assertIn("nfl.com", game["source"])
            else:
                self.assertIn(game["status"], ("ESTIMATED", "PROJECTED"))
                self.assertIn("NOT RELEASED", game["source"])
                self.assertNotIn("http", game["source"])

    def test_the_frame_agrees_with_the_super_bowl(self):
        """Week 18 is 35 days before the Super Bowl, and the frame ends there."""
        for season_year in (2026, 2027, 2028, 2029):
            sb_iso, _, _ = self.cal.super_bowl_for_season(season_year)
            end = self.cal.regular_season_end(season_year)
            delta = (datetime.strptime(sb_iso, "%Y-%m-%d").date()
                     - datetime.strptime(end, "%Y-%m-%d").date()).days
            self.assertEqual(delta, 35, f"{season_year}: Week 18 must be 35 days before the Super Bowl")
            self.assertTrue(
                any(g["league"] == "NFL" and g["date_local"] == end
                    for g in self.bundle["games"]),
                f"{season_year}: the regular-season finale {end} has no NFL record")
