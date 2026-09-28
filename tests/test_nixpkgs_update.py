import io
import unittest
import urllib.error
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import nixpkgs_update
from tests.helpers import http_error, pkg

NOW = "2026-09-30T06:00:00+00:00"

# Trimmed from real logs at nixpkgs-update-logs.nixos.org (2026-09).
HEAD = (
    "Running nixpkgs-update (https://nix-community.org/update-bot/) with UPDATE_INFO: "
)
FAILED = f"""{HEAD}egoboo 2.7.3 -> 2.8.1 https://repology.org/project/egoboo/versions
attrpath: egoboo
Received ExitFailure 1 when running
Running phase: buildPhase
@nix {{ "action": "setPhase", "phase": "buildPhase" }}
\x1b[0mno Makefile or custom buildPhase, doing nothing
/nix/store/dp0z-stdenv-linux/setup: line 1770: cd: source: No such file or directory
"""
PR_OPENED = f"""{HEAD}unciv 4.21.19 -> 4.22.1 https://github.com/yairm210/Unciv/releases
Successfully finished processing
https://api.github.com/repos/NixOS/nixpkgs/pulls/565255
"""
PR_EXISTS = f"""{HEAD}bbedit 15.5.5 -> 16.0.3 https://repology.org/project/bbedit/versions
There might already be an open PR for this update:
- bbedit: 15.5.5 -> 16.0.3
  URL "https://api.github.com/repos/NixOS/nixpkgs/issues/558133"
"""
NO_CHANGE = f"""{HEAD}wesnoth 0 -> 1
[updateScript] Success
The diff was empty after rewrites.
"""
ALREADY_UPDATED = f"""{HEAD}libfilezilla 0.56.1 -> 0.57.0 https://repology.org/project/libfilezilla/versions
Old version 0.56.1" not present in master derivation file with contents: {{
"""


def listing(*dates):
    return "".join(f'<a href="{d}.log">{d}.log</a>\n' for d in dates)


def fake_site(pages):
    """urlopen answering from pages {url suffix: body}; anything else 404."""
    calls = []

    def urlopen(req, timeout):
        url = req.full_url.removeprefix(config.NIXPKGS_UPDATE_LOGS_URL)
        calls.append(url)
        if url not in pages:
            raise http_error(404)
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = pages[url].encode()
        return resp

    return urlopen, calls


class Parse(unittest.TestCase):
    def test_failed(self):
        self.assertEqual(
            nixpkgs_update.parse(FAILED),
            {
                "from": "2.7.3",
                "to": "2.8.1",
                "outcome": "failed",
                # The last meaningful lines, without @nix markers or colours.
                "excerpt": [
                    "Running phase: buildPhase",
                    "no Makefile or custom buildPhase, doing nothing",
                    "/nix/store/dp0z-stdenv-linux/setup: line 1770: cd: source: No "
                    "such file or directory",
                ],
            },
        )

    def test_pr_opened(self):
        result = nixpkgs_update.parse(PR_OPENED)
        self.assertEqual((result["outcome"], result["pr"]), ("prOpened", 565255))

    def test_pr_exists(self):
        result = nixpkgs_update.parse(PR_EXISTS)
        self.assertEqual((result["outcome"], result["pr"]), ("prExists", 558133))

    def test_nothing_to_do(self):
        for log in (NO_CHANGE, ALREADY_UPDATED):
            with self.subTest(log=log[:80]):
                self.assertEqual(nixpkgs_update.parse(log)["outcome"], "noChange")

    def test_unrecognised(self):
        self.assertEqual(nixpkgs_update.parse(f"{HEAD}x 1 -> 2\n")["outcome"], "other")

    def test_superseded(self):
        self.assertTrue(nixpkgs_update.superseded({"to": "2.8.1"}, "2.8.1"))
        self.assertFalse(nixpkgs_update.superseded({"to": "2.8.1"}, "2.7.3"))
        # The updateScript picks the version: can't tell.
        self.assertFalse(nixpkgs_update.superseded({"to": "1"}, "1"))


class AddAttempts(unittest.TestCase):
    def setUp(self):
        self.stderr = io.StringIO()
        for patcher in (
            mock.patch("sys.stderr", self.stderr),
            mock.patch("time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_attempts(self, rows, pages, previous=None):
        nixpkgs = {a: pkg(a) for row in rows for a in row["attrs"]}
        urlopen, calls = fake_site(pages)
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            nixpkgs_update.add_attempts(
                rows, nixpkgs, previous or {"packages": []}, NOW
            )
        return calls

    def test_rows(self):
        rows = [
            {"name": "egoboo", "attrs": ["egoboo"], "nixVersion": "2.7.3"},
            {"name": "unciv", "attrs": ["unciv"], "nixVersion": "4.21.19"},
            {"name": "lincity", "attrs": ["lincity"], "nixVersion": "1.13.1"},
        ]
        self.run_attempts(
            rows,
            {
                "/egoboo/": listing("2026-09-04", "2026-09-15"),
                "/egoboo/2026-09-15.log": FAILED,
                "/unciv/": listing("2026-09-20"),
                "/unciv/2026-09-20.log": PR_OPENED,
            },
        )
        egoboo, unciv, lincity = rows
        self.assertTrue(egoboo["updateFailure"])
        self.assertEqual(egoboo["update"]["date"], "2026-09-15")  # the latest
        self.assertEqual(
            egoboo["update"]["log"],
            f"{config.NIXPKGS_UPDATE_LOGS_URL}/egoboo/2026-09-15.log",
        )
        self.assertFalse(unciv["updateFailure"])
        self.assertEqual(unciv["update"]["outcome"], "prOpened")
        self.assertIsNone(lincity["update"])  # never attempted
        self.assertFalse(lincity["updateFailure"])

    def test_failure_at_a_version_nixpkgs_has_is_superseded(self):
        rows = [{"name": "egoboo", "attrs": ["egoboo"], "nixVersion": "2.8.1"}]
        self.run_attempts(
            rows,
            {"/egoboo/": listing("2026-09-15"), "/egoboo/2026-09-15.log": FAILED},
        )
        self.assertEqual(rows[0]["update"]["outcome"], "superseded")
        self.assertFalse(rows[0]["updateFailure"])

    def test_versioned_sets_use_the_alias(self):
        rows = [
            {
                "name": "python313Packages.requests",
                "attrs": ["python313Packages.requests"],
            }
        ]
        calls = self.run_attempts(rows, {})
        self.assertEqual(calls, ["/python3Packages.requests/"])

    def test_several_attrs_take_the_latest_attempt(self):
        rows = [{"name": "heroic", "attrs": ["heroic", "heroic-unwrapped"]}]
        self.run_attempts(
            rows,
            {
                "/heroic/": listing("2026-09-15"),
                "/heroic/2026-09-15.log": NO_CHANGE,
                "/heroic-unwrapped/": listing("2026-09-20"),
                "/heroic-unwrapped/2026-09-20.log": FAILED,
            },
        )
        self.assertEqual(rows[0]["update"]["attr"], "heroic-unwrapped")
        self.assertTrue(rows[0]["updateFailure"])

    def test_site_down_reuses_previous_and_stops_asking(self):
        rows = [{"name": f"p{i}", "attrs": [f"p{i}"]} for i in range(5)]
        old = {"attr": "p0", "date": "2026-09-01", "outcome": "failed"}
        previous = {"packages": [{"name": "p0", "update": old, "updateFailure": True}]}
        nixpkgs = {row["name"]: pkg(row["name"]) for row in rows}
        with (
            mock.patch.object(config, "RETRY_DELAYS", []),
            mock.patch(
                "urllib.request.urlopen", side_effect=urllib.error.URLError("down")
            ) as urlopen,
        ):
            nixpkgs_update.add_attempts(rows, nixpkgs, previous, NOW)
        self.assertEqual((rows[0]["update"], rows[0]["updateFailure"]), (old, True))
        self.assertIsNone(rows[4]["update"])
        self.assertEqual(
            urlopen.call_count, config.UPDATE_LOGS_MAX_CONSECUTIVE_FAILURES
        )
        self.assertIn(
            "::warning::5 nixpkgs-update log lookups failed", self.stderr.getvalue()
        )
        for r in rows:
            self.assertEqual(r["notRefreshed"]["update"]["since"], NOW)
        self.assertIn("down", rows[0]["notRefreshed"]["update"]["reason"])
