"""The public-site checker: it must tell the CIRCLE site apart from anything else GitHub Pages serves.

On 2026-11-16 the public URL served GitHub's branch-mode Jekyll rendering of README.md while every
CIRCLE workflow was green: the Pages source was "Deploy from a branch", so a second, Jekyll deployment
raced the Actions deployment on each push and won. These tests pin the checker that now runs after
every deploy and on a schedule, against the committed demo/ served under the /circle/ project path.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from tools.check_live_site import PAGES, check_site

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
JEKYLL_README = """<!DOCTYPE html><html lang="en-US"><head><meta charset="UTF-8">
<meta name="generator" content="Jekyll v3.10.0" /><title>CIRCLE | circle</title>
<link rel="stylesheet" href="/circle/assets/css/style.css?v=fdcfd04"></head>
<body><div class="container-lg px-3 my-5 markdown-body"><h1>CIRCLE</h1></div></body></html>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class LiveSiteCheckTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.site = self.root / "circle"
        shutil.copytree(ROOT / "demo", self.site)
        handler = functools.partial(_Quiet, directory=str(self.root))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/circle/"

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        self.temporary.cleanup()

    def stamp(self, commit: str) -> None:
        (self.site / "circle-deploy.json").write_text(json.dumps({"commit": commit}), encoding="utf-8")

    def test_the_committed_site_passes(self):
        self.stamp("abc123")
        self.assertEqual(check_site(self.base, expected_commit="abc123"), [])

    def test_every_published_page_is_checked(self):
        for page in PAGES:
            (self.site / (page or "index.html")).unlink()
            problems = check_site(self.base)
            self.assertTrue(any(p.startswith("/" + page) for p in problems), (page, problems))
            shutil.copy(ROOT / "demo" / (page or "index.html"), self.site / (page or "index.html"))

    def test_a_jekyll_rendered_readme_is_named_as_the_branch_mode_race(self):
        (self.site / "index.html").write_text(JEKYLL_README, encoding="utf-8")
        problems = check_site(self.base)
        self.assertTrue(any("Jekyll" in p and "GitHub Actions" in p for p in problems), problems)

    def test_a_missing_asset_is_reported_by_name(self):
        (self.site / "site.css").unlink()
        (self.site / "first-light-core.js").unlink()
        problems = check_site(self.base)
        self.assertTrue(any("site.css" in p for p in problems), problems)
        self.assertTrue(any("first-light-core.js" in p for p in problems), problems)

    def test_a_stale_or_foreign_deployment_fails_the_commit_check(self):
        self.stamp("old0000")
        problems = check_site(self.base, expected_commit="new1111")
        self.assertTrue(any("old0000" in p and "new1111" in p for p in problems), problems)
        (self.site / "circle-deploy.json").unlink()
        problems = check_site(self.base, expected_commit="new1111")
        self.assertTrue(any("circle-deploy.json" in p for p in problems), problems)

    def test_an_unreachable_site_is_a_problem_not_a_crash(self):
        self.server.shutdown()
        self.server.server_close()
        problems = check_site(self.base, timeout=2)
        self.assertTrue(any("unreachable" in p for p in problems), problems)
        self.server = None

    def test_the_command_line_reports_failure_and_success(self):
        from tools.check_live_site import main
        self.assertEqual(main([self.base, "--expect-commit", "nope"]), 1)
        self.stamp("c0ffee")
        self.assertEqual(main([self.base, "--expect-commit", "c0ffee"]), 0)


@unittest.skipUnless(os.environ.get("CIRCLE_E2E") == "1" and NODE, "set CIRCLE_E2E=1 to open the site on emulated phones")
class PhoneLayoutTest(unittest.TestCase):
    def test_no_page_scrolls_sideways_or_logs_errors_on_a_phone(self):
        done = subprocess.run([NODE, str(ROOT / "tests" / "js" / "site_phone_layout.js")],
                              capture_output=True, text=True, cwd=ROOT, timeout=180)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
