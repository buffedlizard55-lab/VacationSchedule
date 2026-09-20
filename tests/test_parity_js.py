"""Parity test: the browser engine in site/app.js must agree with scripts/lib_windows.py.

The two implementations are written independently (Python stdlib + zoneinfo vs. JS
Date + Intl), so they can drift. This test runs the *actual* site/app.js under Node
via scripts/js_harness.js and diffs its day reports against the Python engine for
every date in the bundle plus the tricky DST boundaries.

If Node is unavailable the test skips rather than passing silently.
"""

import json
import shutil
from datetime import datetime
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_data  # noqa: E402
from lib_windows import day_report  # noqa: E402

HARNESS = ROOT / "scripts" / "js_harness.js"
NODE = shutil.which("node") or shutil.which("nodejs")


def _norm(iso):
    """'2026-10-31T18:00:00+00:00' -> '2026-10-31T18:00:00' (JS harness emits no offset)."""
    return iso[:19]


def _mins(iso_start, iso_end):
    a = datetime.fromisoformat(_norm(iso_start))
    b = datetime.fromisoformat(_norm(iso_end))
    return round((b - a).total_seconds() / 60, 1)


def python_side(date_str):
    rep = day_report(build_data.build()["games"], date_str)
    longest = rep["longest_free_window"]
    return {
        "date": rep["date"],
        "data_coverage": rep["data_coverage"],
        "day_minutes": rep["day_length_minutes"],
        "busy_minutes": rep["busy_minutes"],
        "free_minutes": rep["free_minutes"],
        "is_free_day": rep["is_free_day"],
        "has_high_priority": rep["has_high_priority"],
        "has_unconfirmed_times": rep["has_unconfirmed_times"],
        "unconfirmed_minutes": rep["unconfirmed_minutes"],
        "longest_free_minutes": _mins(longest["start"], longest["end"]) if longest else 0.0,
        "busy_windows_pt": [[_norm(w["start"]), _norm(w["end"])] for w in rep["busy_windows"]],
        "free_windows_pt": [[_norm(w["start"]), _norm(w["end"])] for w in rep["free_windows"]],
    }


@unittest.skipUnless(NODE, "node is not installed")
class TestJsPythonParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = build_data.build()
        # Every date in the bundle, plus the DST boundaries and known edge dates.
        dates = sorted({g["date_local"] for g in bundle["games"]})
        for extra in ("2026-03-08", "2026-11-01", "2027-03-14", "2027-11-07", "2026-01-01", "2026-12-31"):
            if extra not in dates:
                dates.append(extra)
        cls.dates = sorted(dates)

        proc = subprocess.run(
            [NODE, str(HARNESS), *cls.dates],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError("js_harness failed: " + proc.stderr[-2000:])
        cls.js = json.loads(proc.stdout)

    def test_harness_covered_every_date(self):
        self.assertEqual(set(self.js.keys()), set(self.dates))
        self.assertGreater(len(self.dates), 90, "expected a broad date sweep")

    def test_day_reports_match_exactly(self):
        mismatches = []
        for date in self.dates:
            py = python_side(date)
            js = self.js[date]
            for key in py:
                if py[key] != js[key]:
                    mismatches.append(f"{date} {key}: python={py[key]!r} js={js[key]!r}")
        self.assertEqual(mismatches, [], "\n".join(mismatches[:20]))

    def test_dst_days_match(self):
        """23h and 25h days must agree to the minute in both engines."""
        for date, expected in (("2026-03-08", 1380), ("2026-11-01", 1500),
                               ("2027-03-14", 1380), ("2027-11-07", 1500)):
            self.assertEqual(python_side(date)["day_minutes"], expected, f"python {date}")
            self.assertEqual(self.js[date]["day_minutes"], expected, f"js {date}")

    def test_no_date_is_free_when_a_game_exists(self):
        bundle = build_data.build()
        game_dates = {g["date_local"] for g in bundle["games"]}
        for date in game_dates:
            self.assertFalse(self.js[date]["is_free_day"], f"js wrongly free: {date}")
            self.assertFalse(python_side(date)["is_free_day"], f"python wrongly free: {date}")

    def test_unconfirmed_time_dates_agree(self):
        for date in self.dates:
            self.assertEqual(
                python_side(date)["has_unconfirmed_times"],
                self.js[date]["has_unconfirmed_times"],
                date,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
