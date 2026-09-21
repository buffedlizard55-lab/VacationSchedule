"""Tests for the complete official MLB fixture snapshots and the exact-date analysis.

Two layers:

* synthetic-fixture tests, which run everywhere and lock down the CSV contract,
  the strict/regular game-type readings and the analysis switch from a continuous
  season frame to exact fixture dates;
* a real-data test that validates the committed snapshot (all 30 clubs, 162
  regular-season games per club, unique game ids, regular-season dates inside the
  published season frame). It skips when the CI refresh has not committed a
  season yet, and runs for real on every run after the refresh lands.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_vacation  # noqa: E402
import build_data  # noqa: E402

HEADER = (
    "# MLB {year} schedule - all clubs, all game types\n"
    "# source: https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={year}-01-01&endDate={year}-12-31\n"
    "# retrieved_utc: 2026-09-21T00:00:00Z\n"
    "# games: {n} (columns: date_local|start_utc|start_pt|start_et|time_tbd|game_type|away|home|away_id|home_id|venue|status|game_pk)\n"
)


def row(date_local: str, game_type: str, away: str, home: str, away_id: str, home_id: str,
        start_pt: str = "13:05", tbd: bool = False, game_pk: str = "1") -> str:
    return "|".join([
        date_local,
        "" if tbd else f"{date_local}T20:05:00Z",
        "TBD" if tbd else start_pt,
        "TBD" if tbd else "16:05",
        "true" if tbd else "false",
        game_type, away, home, away_id, home_id, "Test Park", "Scheduled", game_pk,
    ])


class TestSnapshotParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._real_verified = build_data.VERIFIED
        build_data.VERIFIED = self.dir
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        build_data.VERIFIED = self._real_verified
        self.tmp.cleanup()

    def _copy_seasons(self) -> None:
        (self.dir / "seasons.json").write_text(
            (ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _write(self, year: int, rows: list[str], summary: dict | None = None) -> None:
        body = HEADER.format(year=year, n=len(rows)) + "\n".join(rows) + "\n"
        (self.dir / f"mlb_schedule_{year}.csv").write_text(body, encoding="utf-8")
        if summary is not None:
            (self.dir / f"mlb_schedule_{year}_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    def test_missing_snapshot_returns_none(self) -> None:
        self.assertIsNone(build_data.load_mlb_season_snapshot(2026))

    def test_rows_are_parsed_with_club_map_and_tbd_flag(self) -> None:
        self._write(2026, [
            row("2026-03-25", "R", "Detroit Tigers", "San Francisco Giants", "116", "137", "13:05", game_pk="10"),
            row("2026-03-26", "S", "Athletics", "Chicago Cubs", "133", "112", "13:05", tbd=True, game_pk="11"),
        ])
        snapshot = build_data.load_mlb_season_snapshot(2026)
        assert snapshot is not None
        self.assertEqual(len(snapshot["rows"]), 2)
        self.assertEqual(snapshot["clubs"]["137"], "San Francisco Giants")
        self.assertEqual(snapshot["tbd"], 1)
        self.assertEqual(snapshot["with_time"], 1)
        # Compact row order: date, start_pt, away, home, venue, type, status, game_pk.
        self.assertEqual(snapshot["rows"][0][1], "13:05")
        self.assertEqual(snapshot["rows"][0][7], "10", "the league game id must survive into the site file")
        self.assertEqual(snapshot["rows"][0][0], "2026-03-25")
        self.assertEqual(snapshot["rows"][1][1], "", "a TBD first pitch must not become a time")

    def test_quiet_dates_exclude_the_all_star_game(self) -> None:
        """A date whose only fixture is the All-Star Game is not a quiet date."""
        self._write(2026, [
            row("2026-03-25", "R", "A", "B", "1", "2", game_pk="1"),
            row("2026-03-26", "R", "C", "D", "3", "4", game_pk="2"),
            row("2026-03-27", "A", "E", "F", "5", "6", game_pk="3"),
            row("2026-03-29", "R", "G", "H", "7", "8", game_pk="4"),
        ])
        snapshot = build_data.load_mlb_season_snapshot(2026)
        assert snapshot is not None
        # 2026-03-27 carries the All-Star Game, so it is NOT quiet; 2026-03-28 has
        # no fixture of any type and is.
        self.assertEqual(snapshot["quiet_dates"], ["2026-03-28"])
        self.assertEqual(snapshot["regular_dates"], ["2026-03-25", "2026-03-26", "2026-03-29"])
        self.assertEqual(snapshot["first_date"], "2026-03-25")
        self.assertEqual(snapshot["last_date"], "2026-03-29")

    def test_quiet_dates_report_a_real_gap(self) -> None:
        self._write(2026, [
            row("2026-03-25", "R", "A", "B", "1", "2", game_pk="1"),
            row("2026-03-27", "R", "C", "D", "3", "4", game_pk="2"),
        ])
        snapshot = build_data.load_mlb_season_snapshot(2026)
        assert snapshot is not None
        self.assertEqual(snapshot["quiet_dates"], ["2026-03-26"])

    def test_club_filter_offers_the_official_roster_only(self) -> None:
        """Exhibition opponents are not MLB clubs and must not join the filter."""
        (self.dir / "mlb_clubs.json").write_text(
            (ROOT / "data" / "verified" / "mlb_clubs.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self._write(2026, [
            row("2026-03-25", "R", "Detroit Tigers", "San Francisco Giants", "116", "137", game_pk="10"),
            row("2026-03-26", "E", "Colombia", "Pittsburgh Pirates", "792", "134", tbd=True, game_pk="11"),
        ])
        snapshot = build_data.load_mlb_season_snapshot(2026)
        assert snapshot is not None
        official = set(snapshot["mlb_club_ids"])
        roster = json.loads((ROOT / "data" / "verified" / "mlb_clubs.json").read_text(encoding="utf-8"))
        self.assertEqual(official, {str(team["id"]) for team in roster["teams"]})
        self.assertEqual(len(official), 30)
        self.assertIn("792", snapshot["clubs"], "the opponent name is still available for the row")
        self.assertNotIn("792", official)

    def test_malformed_row_is_rejected(self) -> None:
        (self.dir / "mlb_schedule_2026.csv").write_text("2026-03-25|only|three\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_data.load_mlb_season_snapshot(2026)

    def test_empty_snapshot_is_rejected(self) -> None:
        (self.dir / "mlb_schedule_2026.csv").write_text(HEADER.format(year=2026, n=0), encoding="utf-8")
        with self.assertRaises(ValueError):
            build_data.load_mlb_season_snapshot(2026)


class TestExactFixtureAnalysis(unittest.TestCase):
    """The analysis must block real fixture dates, not a season-wide envelope."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._real = analyze_vacation.VERIFIED
        analyze_vacation.VERIFIED = self.dir
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        analyze_vacation.VERIFIED = self._real
        self.tmp.cleanup()

    def _copy_seasons(self) -> None:
        (self.dir / "seasons.json").write_text(
            (ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _write(self, year: int, rows: list[str]) -> None:
        (self.dir / f"mlb_schedule_{year}.csv").write_text(
            HEADER.format(year=year, n=len(rows)) + "\n".join(rows) + "\n", encoding="utf-8"
        )

    def test_game_type_readings(self) -> None:
        self._write(2026, [
            row("2026-02-21", "S", "A", "B", "1", "2", game_pk="1"),
            row("2026-02-24", "S", "C", "D", "3", "4", game_pk="2"),
            row("2026-03-25", "R", "E", "F", "5", "6", game_pk="3"),
            row("2026-09-29", "F", "G", "H", "7", "8", game_pk="4"),
            row("2026-07-14", "A", "I", "J", "9", "10", game_pk="5"),
        ])
        strict = analyze_vacation.mlb_fixture_days(2026, True)
        regular = analyze_vacation.mlb_fixture_days(2026, False)
        self.assertEqual(strict, ["2026-02-21", "2026-02-24", "2026-03-25", "2026-07-14", "2026-09-29"])
        self.assertEqual(regular, ["2026-03-25", "2026-07-14", "2026-09-29"],
                         "Spring Training games must drop out of the regular-season reading")

    def test_absence_of_snapshot_keeps_the_frame(self) -> None:
        self.assertIsNone(analyze_vacation.mlb_fixture_days(2026, True))

    def test_blocked_days_use_exact_dates_when_available(self) -> None:
        self._copy_seasons()
        self._write(2026, [
            row("2026-03-25", "R", "E", "F", "5", "6", game_pk="3"),
            row("2026-03-26", "R", "G", "H", "7", "8", game_pk="4"),
        ])
        seasons = json.loads((ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"))
        blocked, provenance = analyze_vacation.blocked_days_for_year(
            2026, seasons["mlb"], count_spring_training=False, section="1"
        )
        self.assertEqual(provenance["mlb_block"]["mode"], "exact_fixtures")
        self.assertIn("2026-03-25", blocked)
        self.assertIn("2026-03-26", blocked)
        # A date with no fixture row inside the season window must NOT be blocked.
        self.assertNotIn("2026-03-27", blocked)
        # Mid-season, before the NFL season opens: the continuous MLB frame would
        # block this date, exact fixtures must not.
        self.assertNotIn("2026-05-15", blocked, "the season frame must not be applied once fixtures are known")

    def test_announced_anchors_block_even_when_the_feed_lacks_them(self) -> None:
        """2027 Opening Night (2027-03-24) is announced but not in the fixture feed."""
        self._copy_seasons()
        self._write(2027, [
            row("2027-03-25", "R", "E", "F", "5", "6", game_pk="3"),
        ])
        days = analyze_vacation.mlb_fixture_days(2027, count_spring_training=False)
        self.assertEqual(days, ["2027-03-24", "2027-03-25"])

    def test_frame_mode_is_reported_when_no_snapshot_exists(self) -> None:
        self._copy_seasons()
        seasons = json.loads((ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"))
        blocked, provenance = analyze_vacation.blocked_days_for_year(
            2026, seasons["mlb"], count_spring_training=True, section="1"
        )
        self.assertEqual(provenance["mlb_block"]["mode"], "season_frame")
        self.assertIn("2026-03-25", blocked)


class TestPostseasonState(unittest.TestCase):
    """The measured postseason state must agree with the reviewed snapshot."""

    def _state(self) -> dict | None:
        path = ROOT / "data" / "verified" / "mlb_postseason_state_2026.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def test_window_dates_cover_the_whole_postseason_window(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        from export_mlb_schedule import postseason_window, window_dates  # noqa: PLC0415

        start, end = postseason_window(2026)
        dates = window_dates(start, end)
        self.assertEqual(dates[0], "2026-09-28")
        self.assertEqual(dates[-1], "2026-10-31")
        self.assertEqual(len(dates), 34, "2026-09-28 to 2026-10-31 inclusive is 34 days")

    def test_measured_state_matches_the_reviewed_snapshot(self) -> None:
        state = self._state()
        if state is None:
            self.skipTest("postseason state not committed yet (CI refresh pending)")
        review = json.loads((ROOT / "data" / "verified" / "mlb_postseason_2026.json").read_text(encoding="utf-8"))
        self.assertEqual(
            state["dates_with_a_reserved_game"],
            sorted(date for date in review["dates_with_a_reserved_game"]),
            "measured reserved dates must equal the reviewed list",
        )
        measured = state["dates_in_window_with_no_game"]
        reviewed = sorted(review["off_days_with_no_possible_game"])
        # Every measured travel day must be a reviewed travel day. The measured list
        # may omit a leading travel day that falls before the first scheduled game
        # (the exporter's window fix lands on the next refresh); nothing else may differ.
        self.assertTrue(set(measured) <= set(reviewed),
                        f"measured {measured} is not a subset of reviewed {reviewed}")
        first_game = min(state["dates_with_a_reserved_game"])
        allowed_missing = {d for d in reviewed if d < first_game}
        self.assertLessEqual(len(set(reviewed) - set(measured)), len(allowed_missing),
                             "only a travel day before the first game may be absent")
        self.assertEqual(state["counts"]["participants_are_placeholders"], True)
        self.assertEqual(state["counts"]["with_published_time"], 0,
                         "no first pitch is published yet; remeasure if this ever changes")


class TestCommittedSnapshots(unittest.TestCase):
    """Validate the CI-committed fixture lists. Skips until a season is committed."""

    def _load(self, year: int) -> dict | None:
        path = ROOT / "data" / "verified" / f"mlb_schedule_{year}_summary.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def test_2026_snapshot_is_consistent_with_the_published_season_frame(self) -> None:
        summary = self._load(2026)
        if summary is None:
            self.skipTest("2026 snapshot not committed yet (CI refresh pending)")
        validation = summary["validation"]
        self.assertTrue(validation["all_30_clubs_present"], "all 30 clubs must appear in the regular season")
        self.assertTrue(validation["regular_season_games_plausible"], "regular-season count out of range")
        self.assertEqual(validation["clubs_with_non_162_regular_season_games"], {})
        self.assertTrue(validation["unique_game_pks"])
        seasons = json.loads((ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"))
        frame = seasons["mlb"]["2026"]
        self.assertEqual(summary["regular_season"]["first_date"], frame["regular_season_start"])
        self.assertEqual(summary["regular_season"]["last_date"], frame["regular_season_end"])

    def test_2027_regular_season_matches_the_released_frame(self) -> None:
        summary = self._load(2027)
        if summary is None:
            self.skipTest("2027 snapshot not committed yet (CI refresh pending)")
        seasons = json.loads((ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"))
        frame = seasons["mlb"]["2027"]
        # The Stats API's 2027 list starts on Opening Day (2027-03-25). Opening
        # Night one day earlier (2027-03-24) was announced separately in MLB's
        # 2026-07-16 release and is therefore an explicit anchor, not a feed row.
        self.assertEqual(summary["regular_season"]["first_date"], frame["regular_season_start"])
        self.assertEqual(summary["regular_season"]["last_date"], frame["regular_season_end"])
        self.assertTrue(summary["validation"]["all_30_clubs_present"])
        if frame.get("opening_night") and frame["opening_night"] != frame["regular_season_start"]:
            self.assertIn(
                frame["opening_night"],
                analyze_vacation.mlb_fixture_days(2027, count_spring_training=False),
                "the announced Opening Night must still block the date",
            )

    def test_day_board_coverage_uses_the_committed_dates(self) -> None:
        """The day board must tell "no game" from "unknown" using the real list."""
        from lib_windows import mlb_frame_coverage  # noqa: PLC0415

        bundle = build_data.build()
        frames = bundle["mlb_frames"]
        frame_2027 = frames.get("2027")
        if not frame_2027 or not frame_2027.get("snapshot_start"):
            self.skipTest("2027 snapshot not committed yet (CI refresh pending)")
        self.assertEqual(mlb_frame_coverage("2027-07-14", frame_2027), "no-game",
                         "the All-Star break has no game, so it must not be reserved")
        self.assertEqual(mlb_frame_coverage("2027-07-13", frame_2027), "game",
                         "the All-Star Game date itself carries a game")
        self.assertEqual(mlb_frame_coverage("2027-03-24", frame_2027), "game",
                         "the announced Opening Night is not in the feed but is a game day, "
                         "so it must stay reserved (IR-39)")
        self.assertEqual(mlb_frame_coverage("2027-10-15", frame_2027), "unknown",
                         "postseason dates are not published for 2027")
        frame_2026 = frames.get("2026")
        if frame_2026 and frame_2026.get("snapshot_start"):
            self.assertEqual(mlb_frame_coverage("2026-07-15", frame_2026), "no-game")
            self.assertEqual(mlb_frame_coverage("2026-07-14", frame_2026), "game",
                             "the 2026 All-Star Game date carries a game")
            self.assertEqual(mlb_frame_coverage("2026-09-29", frame_2026), "game",
                             "the postseason has reserved dates in the committed list")

    def test_committed_csv_dates_are_inside_the_season_window(self) -> None:
        """No fixture may sit outside Spring Training -> postseason end."""
        seasons = json.loads((ROOT / "data" / "verified" / "seasons.json").read_text(encoding="utf-8"))
        checked = 0
        for year in (2026, 2027):
            csv_path = ROOT / "data" / "verified" / f"mlb_schedule_{year}.csv"
            if not csv_path.exists():
                continue
            frame = seasons["mlb"][str(year)]
            start = date.fromisoformat(frame["spring_training_start"])
            end = date.fromisoformat(frame["postseason_end"])
            for raw in csv_path.read_text(encoding="utf-8").splitlines():
                if not raw or raw.startswith("#"):
                    continue
                day = date.fromisoformat(raw.split("|")[0])
                self.assertTrue(start <= day <= end, f"{year}: {day} outside {start}..{end}")
                checked += 1
        if not checked:
            self.skipTest("no committed fixture CSV yet")


if __name__ == "__main__":
    unittest.main()
