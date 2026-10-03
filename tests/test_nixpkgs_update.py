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
# A real version, but no rewriter could update the package (the-legend-of-
# edgar's 1.37 -> 1.38 attempt, 2026-09-26).
CANT_UPDATE = f"""{HEAD}the-legend-of-edgar 1.37 -> 1.38 https://github.com/riksweeney/edgar/releases
attrpath: the-legend-of-edgar
[version]
[version] generic version rewriter does not support multiple hashes
[rustCrateVersion]
[rustCrateVersion] No cargoHash found
[updateScript]
[updateScript] skipping because derivation has no updateScript
The diff was empty after rewrites.
"""
# An updateScript package: "0 -> 1", nixpkgs' version in the package line, and
# the version it updated to in the diff (wesnoth-devel's failed 1.19.24 ->
# 1.19.28 attempt, 2026-09-22).
UPDATE_SCRIPT_FAILED = f"""{HEAD}wesnoth-devel 0 -> 1
attrpath: wesnoth-devel
[updateScript] Success
Going to be running update for following packages:
 - wesnoth-devel-1.19.24

Diff after rewrites:
--- a/pkgs/by-name/we/wesnoth/package.nix
+++ b/pkgs/by-name/we/wesnoth/package.nix
-  version = if enableDevel then "1.19.24" else "1.18.8";
+  version = if enableDevel then "1.19.28" else "1.18.8";

Received ExitFailure 1 when running
-- Configuring incomplete, errors occurred!
"""
# An updateScript that fails before writing a diff: "0 -> 1", and only what
# nixpkgs had in the package line (blackvoxel's 2026-09-27 attempt).
UPDATE_SCRIPT_ERROR = f"""{HEAD}blackvoxel 0 -> 1
attrpath: blackvoxel
[updateScript] Failed with exit code 1
Going to be running update for following packages:
 - blackvoxel-2.5

The update script for blackvoxel-2.5 failed with exit code 1
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
                "was": "2.7.3",
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

    def test_cant_update(self):
        self.assertEqual(
            nixpkgs_update.parse(CANT_UPDATE),
            {
                "outcome": "cantUpdate",
                "from": "1.37",
                "to": "1.38",
                "was": "1.37",
                # Why: the generic rewriter's and the updateScript's reasons.
                "excerpt": [
                    "generic version rewriter does not support multiple hashes",
                    "skipping because derivation has no updateScript",
                ],
            },
        )

    def test_empty_diff_after_update_script_is_nothing_to_update(self):
        # wesnoth's "0 -> 1": its updateScript found nothing newer.
        self.assertEqual(nixpkgs_update.parse(NO_CHANGE)["outcome"], "noChange")

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

    def test_update_script_records_what_nixpkgs_had_and_what_the_diff_tried(self):
        result = nixpkgs_update.parse(UPDATE_SCRIPT_FAILED)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["was"], "wesnoth-devel-1.19.24")
        self.assertEqual((result["from"], result["to"]), ("1.19.24", "1.19.28"))
        # Without a diff (the script itself failed), "0 -> 1" stays.
        error = nixpkgs_update.parse(UPDATE_SCRIPT_ERROR)
        self.assertEqual(error["outcome"], "failed")
        self.assertEqual(error["was"], "blackvoxel-2.5")
        self.assertEqual((error["from"], error["to"]), ("0", "1"))

    def test_superseded_when_nixpkgs_moved_on(self):
        superseded = nixpkgs_update.superseded
        # Plain version from UPDATE_INFO.
        self.assertFalse(superseded({"was": "2.7.3"}, "2.7.3"))  # still there
        self.assertTrue(superseded({"was": "2.7.3"}, "2.8.1"))  # updated
        self.assertTrue(superseded({"was": "2.7.3"}, "2.7.4"))  # past its target
        # Name-version from an updateScript log.
        self.assertFalse(superseded({"was": "wesnoth-devel-1.19.24"}, "1.19.24"))
        self.assertTrue(superseded({"was": "wesnoth-devel-1.19.24"}, "1.19.28"))
        # Not knowable: no record of what nixpkgs had, or no version now.
        self.assertFalse(superseded({"to": "1"}, "1.19.28"))
        self.assertFalse(superseded({"was": "2.7.3"}, None))

    def test_superseded_says_where(self):
        superseded = nixpkgs_update.superseded
        was = {"was": "wesnoth-devel-1.19.24"}
        self.assertEqual(superseded(was, "1.19.28"), "nixos-unstable")
        # Merged on master, the channel not there yet.
        self.assertEqual(superseded(was, "1.19.24", "1.19.28"), "master")
        # The channel counts first when both have moved on.
        self.assertEqual(superseded(was, "1.19.28", "1.19.30"), "nixos-unstable")
        self.assertIsNone(superseded(was, "1.19.24", None))


class AddAttempts(unittest.TestCase):
    def setUp(self):
        self.stderr = io.StringIO()
        for patcher in (
            mock.patch("sys.stderr", self.stderr),
            mock.patch("time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_attempts(self, rows, pages, previous=None, ignored=None, community=()):
        nixpkgs = {a: pkg(a) for row in rows for a in row["attrs"]}
        urlopen, calls = fake_site(pages)
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            nixpkgs_update.add_attempts(
                rows, nixpkgs, previous or {"packages": []}, NOW, ignored, community
            )
        return calls

    def test_cant_update_is_not_a_failure_until_nixpkgs_moves_on(self):
        rows = [{"name": "edgar", "attrs": ["edgar"], "nixVersion": "1.37"}]
        pages = {"/edgar/": listing("2026-09-26"), "/edgar/2026-09-26.log": CANT_UPDATE}
        self.run_attempts(rows, pages)
        self.assertEqual(rows[0]["update"]["outcome"], "cantUpdate")
        self.assertFalse(rows[0]["updateFailure"])
        # Updated by hand: the attempt no longer matters.
        rows = [{"name": "edgar", "attrs": ["edgar"], "nixVersion": "1.38"}]
        self.run_attempts(rows, pages)
        update = rows[0]["update"]
        self.assertEqual(update["outcome"], "superseded")
        self.assertEqual(update["supersededOutcome"], "cantUpdate")

    def test_ignored_version_is_superseded_with_its_reason(self):
        """xskat: the bot tried a 4.0-9 upstream never released."""
        rows = [{"name": "egoboo", "attrs": ["egoboo"], "nixVersion": "2.7.3"}]
        pages = {"/egoboo/": listing("2026-09-15"), "/egoboo/2026-09-15.log": FAILED}
        self.run_attempts(rows, pages, ignored={"egoboo": {"2.8.1": "Never released."}})
        update = rows[0]["update"]
        self.assertEqual(update["outcome"], "superseded")
        self.assertEqual(update["supersededOn"], "ignored")
        self.assertEqual(update["reason"], "Never released.")
        self.assertEqual(update["to"], "2.8.1")  # still says what it tried
        self.assertFalse(rows[0]["updateFailure"])
        self.assertNotIn("the rule can go", self.stderr.getvalue())

    def test_other_versions_still_fail_and_the_rule_can_go(self):
        rows = [{"name": "egoboo", "attrs": ["egoboo"], "nixVersion": "2.7.3"}]
        pages = {"/egoboo/": listing("2026-09-15"), "/egoboo/2026-09-15.log": FAILED}
        self.run_attempts(rows, pages, ignored={"egoboo": {"2.8.0": "Never released."}})
        self.assertEqual(rows[0]["update"]["outcome"], "failed")
        self.assertTrue(rows[0]["updateFailure"])
        self.assertIn(
            "::notice::ignoredUpdates.egoboo: the bot's latest attempt isn't at "
            "2.8.0 anymore; the rule can go",
            self.stderr.getvalue(),
        )

    def test_a_community_rule_says_so(self):
        rows = [{"name": "egoboo", "attrs": ["egoboo"], "nixVersion": "2.7.3"}]
        pages = {"/egoboo/": listing("2026-09-15"), "/egoboo/2026-09-15.log": FAILED}
        rules = {"egoboo": {"2.8.1": "Never released.", "2.8.0": "Old."}}
        community = {("egoboo", "2.8.1"), ("egoboo", "2.8.0")}
        self.run_attempts(rows, pages, ignored=rules, community=community)
        self.assertTrue(rows[0]["update"]["community"])
        # Stale community rules are listed by community-check, not here.
        self.assertNotIn("the rule can go", self.stderr.getvalue())

    def test_update_script_error_is_ignored_only_while_up_to_date(self):
        """blackvoxel: nix-update fails at 2.5 (the newest), then 2.6 comes out."""
        pages = {
            "/blackvoxel/": listing("2026-09-27"),
            "/blackvoxel/2026-09-27.log": UPDATE_SCRIPT_ERROR,
        }
        rules = {"blackvoxel": {"2.5": "Chases an older v2.42 tag."}}
        row = {
            "name": "blackvoxel",
            "attrs": ["blackvoxel"],
            "nixVersion": "2.5",
            "nixStatus": "newest",
        }
        self.run_attempts(
            [row], pages, ignored=rules, community={("blackvoxel", "2.5")}
        )
        self.assertEqual(row["update"]["outcome"], "superseded")
        self.assertEqual(row["update"]["supersededOn"], "ignored")
        self.assertTrue(row["update"]["community"])
        self.assertFalse(row["updateFailure"])
        self.assertNotIn("the rule can go", self.stderr.getvalue())
        # Once 2.6 is out, the row is outdated and the failure counts again.
        outdated = {**row, "nixStatus": "outdated", "refVersion": "2.6"}
        self.run_attempts(
            [outdated], pages, previous={"packages": [row]}, ignored=rules
        )
        self.assertEqual(outdated["update"]["outcome"], "failed")
        self.assertTrue(outdated["updateFailure"])

    def test_only_failures_are_ignored(self):
        attempt = {"outcome": "prOpened", "to": "2.8.1"}
        self.assertIsNone(nixpkgs_update.ignored(attempt, {"2.8.1": "x"}))
        self.assertIsNone(nixpkgs_update.ignored({"outcome": "failed"}, None))
        # The placeholder "1" of "0 -> 1" never matches a rule called "1".
        script = {"outcome": "failed", "to": "1", "was": "blackvoxel-2.5"}
        self.assertIsNone(nixpkgs_update.ignored(script, {"1": "x"}))

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

    def test_update_script_failure_clears_once_nixpkgs_updates(self):
        """wesnoth-devel: the bot failed 1.19.24 -> 1.19.28, then a manual PR
        got 1.19.28 merged (built on master), then into the channel, before
        the bot tried again."""
        pages = {
            "/wesnoth-devel/": listing("2026-09-22"),
            "/wesnoth-devel/2026-09-22.log": UPDATE_SCRIPT_FAILED,
        }
        stages = (
            # channel, master (from Hydra): failing?, superseded where
            ("1.19.24", None, True, None),  # nothing merged yet
            ("1.19.24", "1.19.28", False, "master"),  # merged
            ("1.19.28", None, False, "nixos-unstable"),  # in the channel
        )
        for nix_version, master, failing, where in stages:
            with self.subTest(nix_version=nix_version, master=master):
                row = {
                    "name": "wesnoth-devel",
                    "attrs": ["wesnoth-devel"],
                    "nixVersion": nix_version,
                }
                if master:
                    row["master"] = master
                self.run_attempts([row], pages)
                self.assertEqual(row["updateFailure"], failing)
                self.assertEqual(
                    row["update"]["outcome"], "failed" if failing else "superseded"
                )
                self.assertEqual(row["update"].get("supersededOn"), where)

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


class ReuseLogs(unittest.TestCase):
    """A sync reads a log once: next time, if the bot's latest attempt is the
    same (same attribute and date, read by the same rules), it takes the
    previous reading instead of downloading it again, and judges it afresh
    against nixpkgs and the rules now."""

    EGOBOO = {"/egoboo/": listing("2026-09-15"), "/egoboo/2026-09-15.log": FAILED}
    LOG = "/egoboo/2026-09-15.log"

    def setUp(self):
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch("time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def sync(self, previous=None, pages=None, ignored=None, community=(), **row):
        """One run of add_attempts for egoboo: (its row, the URLs fetched)."""
        rows = [{"name": "egoboo", "attrs": ["egoboo"], "nixVersion": "2.7.3", **row}]
        nixpkgs = {a: pkg(a) for a in rows[0]["attrs"]}
        urlopen, calls = fake_site(pages or self.EGOBOO)
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            nixpkgs_update.add_attempts(
                rows, nixpkgs, {"packages": previous or []}, NOW, ignored, community
            )
        return rows[0], calls

    def test_the_same_attempt_isnt_downloaded_again(self):
        first, calls = self.sync()
        self.assertIn(self.LOG, calls)
        self.assertEqual(first["update"]["parser"], nixpkgs_update.PARSER)
        second, calls = self.sync(previous=[first])
        self.assertEqual(calls, ["/egoboo/"])  # the listing, not the log
        self.assertEqual(second["update"], first["update"])
        self.assertTrue(second["updateFailure"])

    def test_a_new_attempt_is(self):
        first, _ = self.sync()
        pages = {
            **self.EGOBOO,
            "/egoboo/": listing("2026-09-15", "2026-09-25"),
            "/egoboo/2026-09-25.log": PR_OPENED,
        }
        second, calls = self.sync(previous=[first], pages=pages)
        self.assertIn("/egoboo/2026-09-25.log", calls)
        self.assertEqual(second["update"]["outcome"], "prOpened")

    def test_read_again_when_the_rules_changed(self):
        first, _ = self.sync()
        with mock.patch.object(nixpkgs_update, "PARSER", nixpkgs_update.PARSER + 1):
            second, calls = self.sync(previous=[first])
        self.assertIn(self.LOG, calls)
        # And data from before PARSER existed is read again too.
        old = {k: v for k, v in first["update"].items() if k != "parser"}
        third, calls = self.sync(previous=[{**first, "update": old}])
        self.assertIn(self.LOG, calls)
        self.assertEqual(third["update"]["parser"], nixpkgs_update.PARSER)

    def test_judged_afresh_superseded(self):
        # Superseded last time: nixpkgs had moved on.
        first, _ = self.sync(nixVersion="2.8.1")
        self.assertEqual(first["update"]["outcome"], "superseded")
        self.assertEqual(first["update"]["supersededOn"], "nixos-unstable")
        # Reused, it's judged on today's nixpkgs: still superseded...
        second, calls = self.sync(previous=[first], nixVersion="2.8.1")
        self.assertEqual(calls, ["/egoboo/"])
        self.assertEqual(second["update"], first["update"])
        # ...and as the log reads when nothing supersedes it.
        third, _ = self.sync(previous=[first])
        self.assertEqual(third["update"]["outcome"], "failed")
        for judged in nixpkgs_update.JUDGED:
            self.assertNotIn(judged, third["update"])
        self.assertTrue(third["updateFailure"])

    def test_judged_afresh_ignored(self):
        rules = {"egoboo": {"2.8.1": "Never released."}}
        community = {("egoboo", "2.8.1")}
        first, _ = self.sync(ignored=rules, community=community)
        self.assertEqual(first["update"]["supersededOn"], "ignored")
        self.assertTrue(first["update"]["community"])
        # The rule went away: the failure counts again, nothing of the rule left.
        second, calls = self.sync(previous=[first])
        self.assertEqual(calls, ["/egoboo/"])
        self.assertEqual(second["update"]["outcome"], "failed")
        self.assertNotIn("reason", second["update"])
        self.assertNotIn("community", second["update"])
        # Reused and still ignored: as a fresh read would be.
        third, _ = self.sync(previous=[first], ignored=rules, community=community)
        self.assertEqual(third["update"], first["update"])

    def test_the_same_as_reading_the_log(self):
        for log in (FAILED, PR_OPENED, CANT_UPDATE):
            with self.subTest(log=log.splitlines()[-1][:40]):
                pages = {"/egoboo/": listing("2026-09-15"), self.LOG: log}
                first, _ = self.sync(pages=pages)
                second, calls = self.sync(previous=[first], pages=pages)
                self.assertEqual(calls, ["/egoboo/"])
                self.assertEqual(second["update"], first["update"])
                self.assertEqual(second["updateFailure"], first["updateFailure"])

    def test_read_again_when_unsure(self):
        first, _ = self.sync(nixVersion="2.8.1")
        broken = {k: v for k, v in first["update"].items() if k != "supersededOutcome"}
        _, calls = self.sync(previous=[{**first, "update": broken}])
        self.assertIn(self.LOG, calls)

    def test_another_attribute_is_read(self):
        # The stored attempt is egoboo's; egoboo-unwrapped's is its own.
        first, _ = self.sync()
        pages = {
            **self.EGOBOO,
            "/egoboo-unwrapped/": listing("2026-09-15"),
            "/egoboo-unwrapped/2026-09-15.log": FAILED,
        }
        _, calls = self.sync(
            previous=[first], pages=pages, attrs=["egoboo", "egoboo-unwrapped"]
        )
        self.assertNotIn(self.LOG, calls)
        self.assertIn("/egoboo-unwrapped/2026-09-15.log", calls)

    def test_a_reused_attempt_is_a_copy(self):
        first, _ = self.sync()
        excerpt = list(first["update"]["excerpt"])
        second, _ = self.sync(previous=[first])
        second["update"]["excerpt"].append("changed")
        second["update"]["outcome"] = "changed"
        self.assertEqual(first["update"]["excerpt"], excerpt)
        self.assertEqual(first["update"]["outcome"], "failed")
