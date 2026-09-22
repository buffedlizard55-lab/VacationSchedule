"""Tests for the 2026-09-21 line-by-line verification pass and the wider radio scope.

Covers:
* MLB postseason clinch facts (berths vs division titles; no invented matchups/times).
* Super Bowl LXIII's verified date flowing through the NFL calendar.
* Other Bay Area live-radio sports (Warriors NBA, Valkyries WNBA): high priority,
  counted busy in the `all` scope only, never leaking into Sections 1-3.
* Streaming-only exclusions (Sharks Audio Network, Audacy-only Valkyries games)
  never block an AM/FM listener's free time.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_data import build, from_other_radio_sports  # noqa: E402
from analyze_vacation import analyze, blocked_days_for_year, other_radio_spans  # noqa: E402
from lib_windows import day_report, filter_scope, game_in_scope, DEFAULT_DURATIONS, TBD_ENVELOPE_PT  # noqa: E402
from nfl_calendar import SUPER_BOWL_BY_YEAR  # noqa: E402


def load_verified(name):
    return json.loads((ROOT / "data" / "verified" / name).read_text(encoding="utf-8"))


class TestPostseasonClinchFacts(unittest.TestCase):
    def setUp(self):
        self.payload = load_verified("mlb_postseason_2026.json")
        self.clinch = self.payload["clinch_status"]

    def test_six_berths_and_three_divisions(self):
        self.assertEqual(len(self.clinch["clinched_postseason_berth"]), 6)
        self.assertEqual(len(self.clinch["clinched_division"]), 3)

    def test_rays_are_not_listed_as_division_winners(self):
        # The 2026-09-20 snapshot wrongly listed Tampa Bay as AL East champion.
        self.assertFalse(any("Rays" in d and "AL East" in d for d in self.clinch["clinched_division"]))
        self.assertTrue(any("Rays" in b for b in self.clinch["clinched_postseason_berth"]))

    def test_braves_nl_east_is_recorded(self):
        self.assertTrue(any("Braves" in d and "NL East" in d for d in self.clinch["clinched_division"]))

    def test_no_matchup_or_time_is_invented(self):
        self.assertIn("0 set", self.clinch["resolution_progress"]["first_pitch_times"])
        self.assertIn("0 of 4", self.clinch["resolution_progress"]["matchups"])
        for date_iso in self.payload["dates_with_a_reserved_game"]:
            self.assertTrue(date_iso.startswith("2026-09") or date_iso.startswith("2026-10"), date_iso)

    def test_off_days_stay_off(self):
        off = set(self.payload["off_days_with_no_possible_game"])
        self.assertIn("2026-10-02", off)
        self.assertIn("2026-10-25", off)
        self.assertFalse(off & set(self.payload["dates_with_a_reserved_game"]))


class TestSuperBowlDates(unittest.TestCase):
    def test_lxiii_is_estimated_everywhere_consistently(self):
        # Host/year official; exact day disputed across secondaries (WJHL/KLAS
        # says Feb 11 announced, NBC says no firm date, nfl.com names no day,
        # Forbes citation 404s). planning assumption, not a released date.
        # Re-verified 2026-09-22; see docs/IRREGULARITIES.md IR-12.
        self.assertEqual(SUPER_BOWL_BY_YEAR[2029][:2], ("2029-02-11", "ESTIMATED"))
        seasons = load_verified("seasons.json")
        anchor = seasons["nfl"]["2028"]["verified_anchors"]
        self.assertEqual(anchor["super_bowl"], "2029-02-11")
        self.assertIn("ESTIMATED", anchor["super_bowl_status"])

    def test_2030_super_bowl_still_estimated(self):
        self.assertEqual(SUPER_BOWL_BY_YEAR[2030][1], "ESTIMATED")


class TestOtherRadioSports(unittest.TestCase):
    def setUp(self):
        self.payload = load_verified("other_radio_sports.json")
        self.games, self.unresolved = from_other_radio_sports()
        self.bundle = build()

    def test_warriors_and_valkyries_present_high_priority(self):
        leagues = {g["league"] for g in self.games}
        self.assertEqual(leagues, {"NBA", "WNBA"})
        self.assertTrue(all(g["priority"] == "high" for g in self.games))
        self.assertTrue(any("Warriors" in g["label"] for g in self.games))
        self.assertTrue(any("Valkyries" in g["label"] for g in self.games))

    def test_warriors_schedule_shape(self):
        w = [g for g in self.games if g["league"] == "NBA"]
        # 6 preseason + 80 regular-season rows transcribed 2026-09-21 (nominal 82;
        # up to two rows unreconciled - see IR-37). Count is asserted so a future
        # edit cannot silently drop games.
        self.assertEqual(len(w), 86)
        self.assertEqual(sum(1 for g in w if "preseason" in g["detail"]), 6)
        dates = sorted(g["date_local"] for g in w)
        self.assertEqual(dates[0], "2026-10-04")  # first preseason tip (ET 7pm = PT 4pm)
        self.assertEqual(dates[-1], "2027-04-11")
        self.assertEqual(len(set(dates)), len(dates), "one Warriors row per date")

    def test_streaming_only_games_do_not_block(self):
        # Audacy-only Valkyries rows are excluded from the game list entirely.
        v = [g for g in self.games if g["league"] == "WNBA"]
        listed = self.payload["valkyries"]["games_2026"]
        streaming = [r for r in listed if not r.get("on_957")]
        self.assertTrue(streaming)
        self.assertEqual(len(v), sum(1 for r in listed if r.get("on_957")) + 5)  # +5 playoff windows
        for row in streaming:
            on_date = [g for g in v if g["date_local"] == row["date"]]
            self.assertFalse(
                any(row["opponent"] in g["label"] for g in on_date),
                f"streaming-only game {row['date']} {row['opponent']} must not be a busy interval",
            )

    def test_sharks_never_block(self):
        self.assertFalse(any("Sharks" in g["label"] for g in self.bundle["games"]))
        radio = self.bundle["radio"]["stations"]
        sharks = [s for s in radio if "Sharks" in s["call_letters"]]
        self.assertTrue(sharks and sharks[0].get("excluded"))

    def test_sections_1_3_are_untouched(self):
        for g in self.games:
            self.assertEqual(g.get("sections") or [], [], f"{g['label']} must not join any requested section")
        for scope in ("1", "2", "3"):
            self.assertEqual(filter_scope(self.games, scope), [])
            self.assertTrue(all(game_in_scope(g, scope) is False for g in self.games))
        self.assertTrue(all(game_in_scope(g, "all") for g in self.games))

    def test_day_report_busy_under_all_and_free_under_section_1(self):
        game = next(g for g in self.games if g["league"] == "NBA" and g["date_local"] == "2026-10-21")
        busy = day_report([game], "2026-10-21", scope="all")
        quiet = day_report([game], "2026-10-21", scope="1")
        self.assertFalse(busy["is_free_day"])
        self.assertTrue(quiet["is_free_day"])

    def test_vacation_analysis_only_all_scope_blocks(self):
        seasons = load_verified("seasons.json")
        for year in (2026, 2027, 2028, 2029):
            _, prov_all = blocked_days_for_year(year, seasons["mlb"], True, "all")
            _, prov_3 = blocked_days_for_year(year, seasons["mlb"], True, "3")
            self.assertTrue(prov_all["other_radio_blocks"])
            self.assertEqual(prov_3["other_radio_blocks"], [])

    def test_future_warriors_envelopes_are_estimated(self):
        spans = other_radio_spans(2028)
        nba = [s for s in spans if "NBA season" in s["label"]]
        self.assertTrue(all(s["status"] == "ESTIMATED" for s in nba))
        verified = [s for s in other_radio_spans(2027) if s["status"] == "VERIFIED"]
        self.assertTrue(any("2026-27" in s["label"] for s in verified))

    def test_durations_and_envelopes_cover_new_leagues(self):
        for league in ("NBA", "WNBA"):
            self.assertIn(league, DEFAULT_DURATIONS)
            self.assertIn(league, TBD_ENVELOPE_PT)
        bundle_meta = self.bundle["_meta"]
        self.assertEqual(bundle_meta["durations_minutes"]["NBA"], DEFAULT_DURATIONS["NBA"])
        self.assertGreaterEqual(self.bundle["_meta"]["counts"]["by_league"]["WNBA"], 5)

    def test_unresolved_coverage_is_disclosed(self):
        labels = " | ".join(u["label"] for u in self.unresolved)
        self.assertIn("streaming-only", labels)
        self.assertIn("USF", labels)
        self.assertIn("playoffs beyond the first round", labels)


if __name__ == "__main__":
    unittest.main()
