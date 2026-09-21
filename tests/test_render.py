"""Runs the jsdom render check (tests/render_check.js) as part of the Python suite.

This is the only test that executes site/app.js as a *page* -- loading the real
index.html into a DOM, firing DOMContentLoaded, clicking the real navigation buttons
and asserting what the user would see. Everything else tests the engine as a library.

Skips if node or jsdom are unavailable, rather than passing silently.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node") or shutil.which("nodejs")
RENDER_CHECK = ROOT / "tests" / "render_check.js"
JSDOM = ROOT / "node_modules" / "jsdom"


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(JSDOM.is_dir(), "jsdom is not installed (npm install --no-save jsdom)")
class TestSiteRenders(unittest.TestCase):
    def test_render_check_passes(self):
        proc = subprocess.run(
            [NODE, str(RENDER_CHECK)],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr[-3000:])
        self.assertIn("0 failed", proc.stdout)
        # Guard against the check silently passing by asserting nothing.
        self.assertGreaterEqual(proc.stdout.count("PASS"), 20, proc.stdout)

    def test_render_check_covers_the_reported_regression(self):
        src = RENDER_CHECK.read_text(encoding="utf-8")
        self.assertIn("2026-09-29", src, "the Wild Card regression date must be covered")
        self.assertIn("NO KNOWN CONFLICT", src, "missing coverage must not be called guaranteed free")


if __name__ == "__main__":
    unittest.main(verbosity=2)
