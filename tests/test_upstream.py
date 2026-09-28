import io
import json
import unittest
import urllib.error
from unittest import mock

from nixkeeper.changes import is_outdated
from nixkeeper.sources import github, upstream
from tests.helpers import response

WESNOTH_TAGS = ["1.19.28", "1.18.8", "1.19.27", "1.19.9", "1.19.24", "1.18.7"]
CHECK = {"github": "wesnoth/wesnoth", "tags": r"^(1\.19\.[0-9]+)$"}


def row(name="wesnoth-devel", nix="1.19.24", status="devel", ref="1.19.24"):
    return {"name": name, "nixVersion": nix, "nixStatus": status, "refVersion": ref}


class Versions(unittest.TestCase):
    def test_ordering(self):
        for older, newer in (
            ("1.19.9", "1.19.28"),
            ("1.19.28", "1.20.0"),
            ("1.0rc1", "1.0.1"),
            ("2.1.20221123", "2.1.20260913"),
        ):
            with self.subTest(older=older, newer=newer):
                self.assertTrue(upstream.is_newer(newer, older))
                self.assertFalse(upstream.is_newer(older, newer))
        self.assertFalse(upstream.is_newer("1.0", None))  # nothing to compare

    def test_latest_matching_tag(self):
        self.assertEqual(upstream.latest(WESNOTH_TAGS, CHECK["tags"]), "1.19.28")
        self.assertEqual(
            upstream.latest(["v2.3.0", "v2.10.1"], r"^v([0-9.]+)$"), "2.10.1"
        )
        # Without a capture group the whole match is the version.
        self.assertEqual(upstream.latest(["1.2", "1.10"], r"^[0-9.]+$"), "1.10")
        self.assertIsNone(upstream.latest(["nightly"], r"^[0-9.]+$"))


class Apply(unittest.TestCase):
    def test_newer_release_makes_it_outdated(self):
        r = row()
        upstream.apply(r, {"version": "1.19.28", "repo": "wesnoth/wesnoth"})
        self.assertTrue(r["upstream"]["newer"])
        self.assertEqual(r["refVersion"], "1.19.28")
        self.assertTrue(is_outdated(r))

    def test_up_to_date(self):
        r = row()
        upstream.apply(r, {"version": "1.19.24", "repo": "wesnoth/wesnoth"})
        self.assertFalse(r["upstream"]["newer"])
        self.assertEqual(r["refVersion"], "1.19.24")
        self.assertFalse(is_outdated(r))

    def test_repology_already_ahead_keeps_its_version(self):
        r = row(status="outdated", ref="1.19.30")
        upstream.apply(r, {"version": "1.19.28", "repo": "wesnoth/wesnoth"})
        self.assertEqual(r["refVersion"], "1.19.30")


class AddChecks(unittest.TestCase):
    def setUp(self):
        self.stderr = io.StringIO()
        for patcher in (
            mock.patch("sys.stderr", self.stderr),
            mock.patch.object(github, "token", return_value="t"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_checks(self, rows, checks, tags=None, error=None, previous=None):
        kwargs = {"side_effect": error} if error else {"return_value": tags}
        with mock.patch.object(github, "latest_tags", **kwargs) as latest_tags:
            upstream.add_checks(rows, checks, previous or {"packages": []})
        return latest_tags

    def test_check(self):
        rows = [row(), row("wesnoth", "1.18.8", "newest", "1.18.8")]
        latest_tags = self.run_checks(
            rows,
            {"wesnoth-devel": CHECK, "not-tracked": CHECK},
            {"wesnoth/wesnoth": WESNOTH_TAGS},
        )
        latest_tags.assert_called_once_with("t", ["wesnoth/wesnoth"])
        self.assertEqual(
            rows[0]["upstream"],
            {
                "version": "1.19.28",
                "repo": "wesnoth/wesnoth",
                "url": "https://github.com/wesnoth/wesnoth/tags",
                "newer": True,
            },
        )
        self.assertNotIn("upstream", rows[1])  # no check for it
        self.assertIn("not-tracked: not a tracked package", self.stderr.getvalue())

    def test_failure_keeps_previous_result(self):
        old = {"version": "1.19.26", "repo": "wesnoth/wesnoth", "newer": True}
        previous = {"packages": [{"name": "wesnoth-devel", "upstream": old}]}
        for kwargs in (
            {"error": urllib.error.URLError("down")},
            {"tags": {}},  # GitHub couldn't read the repository
            {"tags": {"wesnoth/wesnoth": ["nightly"]}},  # nothing matches
        ):
            with self.subTest(**kwargs):
                rows = [row()]
                self.run_checks(
                    rows, {"wesnoth-devel": CHECK}, previous=previous, **kwargs
                )
                self.assertEqual(rows[0]["upstream"]["version"], "1.19.26")
                self.assertEqual(rows[0]["refVersion"], "1.19.26")
        self.assertIn(
            "::warning::update check for wesnoth-devel", self.stderr.getvalue()
        )


class LatestTags(unittest.TestCase):
    def test_query_and_answer(self):
        resp = response(
            {
                "data": {
                    "r0": {"refs": {"nodes": [{"name": "v1.1"}, {"name": "v1.0"}]}},
                    "r1": None,  # not found
                }
            }
        )
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            tags = github.latest_tags("t", ["a/one", "b/missing"])
        self.assertEqual(tags, {"a/one": ["v1.1", "v1.0"]})
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(
            body["variables"], {"o0": "a", "n0": "one", "o1": "b", "n1": "missing"}
        )
        self.assertIn("TAG_COMMIT_DATE", body["query"])
