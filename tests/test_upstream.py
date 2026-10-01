import io
import json
import unittest
import urllib.error
from unittest import mock

from nixkeeper import config
from nixkeeper.changes import is_outdated
from nixkeeper.sources import github, upstream
from tests.helpers import http_error, response

NOW = "2026-09-30T06:00:00+00:00"

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
            upstream.add_checks(rows, checks, previous or {"packages": []}, NOW)
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
                "label": "wesnoth/wesnoth tags",
                "url": "https://github.com/wesnoth/wesnoth/tags",
                "newer": True,
                "checkedAt": NOW,
            },
        )
        self.assertNotIn("upstream", rows[1])  # no check for it
        # A check for a package that isn't tracked doesn't run (listcheck.py
        # reports it with the lists).
        self.assertNotIn("not-tracked", self.stderr.getvalue())

    def test_failure_keeps_previous_result_and_says_so(self):
        old = {"version": "1.19.26", "repo": "wesnoth/wesnoth", "newer": True}
        previous = {"packages": [{"name": "wesnoth-devel", "upstream": old}]}
        for reason, kwargs in (
            ("GitHub request failed", {"error": urllib.error.URLError("down")}),
            ("renamed or deleted?", {"tags": {}}),
            ("matches", {"tags": {"wesnoth/wesnoth": ["nightly"]}}),
        ):
            with self.subTest(reason=reason):
                rows = [row()]
                self.run_checks(
                    rows, {"wesnoth-devel": CHECK}, previous=previous, **kwargs
                )
                self.assertEqual(rows[0]["upstream"]["version"], "1.19.26")
                self.assertEqual(rows[0]["refVersion"], "1.19.26")
                failing = rows[0]["notRefreshed"]["upstream"]
                self.assertEqual(failing["since"], NOW)
                self.assertIn(reason, failing["reason"])
        self.assertIn(
            "::warning::update check for wesnoth-devel", self.stderr.getvalue()
        )

    def test_no_token_counts_as_failing(self):
        rows = [row()]
        with mock.patch.object(github, "token", return_value=None):
            self.run_checks(rows, {"wesnoth-devel": CHECK}, {})
        self.assertNotIn("upstream", rows[0])  # nothing to fall back on
        self.assertIn("no GITHUB_TOKEN", rows[0]["notRefreshed"]["upstream"]["reason"])

    def test_failing_since_carries_over(self):
        since = "2026-09-28T06:00:00+00:00"
        previous = {
            "packages": [
                {
                    "name": "wesnoth-devel",
                    "notRefreshed": {"upstream": {"since": since, "reason": "x"}},
                }
            ]
        }
        rows = [row()]
        self.run_checks(rows, {"wesnoth-devel": CHECK}, {}, previous=previous)
        self.assertEqual(rows[0]["notRefreshed"]["upstream"]["since"], since)
        # Working again: no marker.
        rows = [row()]
        self.run_checks(
            rows,
            {"wesnoth-devel": CHECK},
            {"wesnoth/wesnoth": WESNOTH_TAGS},
            previous=previous,
        )
        self.assertNotIn("notRefreshed", rows[0])


# Trimmed from https://www.barebones.com/support/bbedit/updates.html (2026-09).
BBEDIT_PAGE = """<h2>BBEdit 16.0.3</h2><p>Fixed a crash in BBEdit 16.0.2 when...</p>
<h2>BBEdit 15.5.5</h2><p>Requires macOS 12 or later.</p><h2>BBEdit 14.6.9</h2>"""
BBEDIT = {
    "url": "https://www.barebones.com/support/bbedit/updates.html",
    "pattern": r"BBEdit ([0-9]+\.[0-9]+\.[0-9]+)",
}


class PageChecks(unittest.TestCase):
    def setUp(self):
        self.stderr = io.StringIO()
        for patcher in (
            mock.patch("sys.stderr", self.stderr),
            mock.patch("time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_highest_version_anywhere_on_the_page(self):
        self.assertEqual(
            upstream.latest_on_page(BBEDIT_PAGE, BBEDIT["pattern"]), "16.0.3"
        )
        # Order on the page doesn't matter.
        reversed_page = "BBEdit 15.5.5 ... BBEdit 16.0.3"
        self.assertEqual(
            upstream.latest_on_page(reversed_page, BBEDIT["pattern"]), "16.0.3"
        )

    def run_check(self, rows, urlopen, previous=None):
        with (
            mock.patch("urllib.request.urlopen", **urlopen),
            mock.patch.object(github, "token", return_value="t"),
        ):
            upstream.add_checks(
                rows, {"bbedit": BBEDIT}, previous or {"packages": []}, NOW
            )

    def test_page_check(self):
        page = response("x")
        page.read.return_value = BBEDIT_PAGE.encode()
        rows = [row("bbedit", "16.0.2", "newest", "16.0.2")]
        self.run_check(rows, {"return_value": page})
        self.assertEqual(
            rows[0]["upstream"],
            {
                "version": "16.0.3",
                "label": "www.barebones.com",
                "url": BBEDIT["url"],
                "newer": True,
                "checkedAt": NOW,
            },
        )
        self.assertEqual(rows[0]["refVersion"], "16.0.3")

    def test_page_problems_keep_previous_result(self):
        old = {"version": "16.0.3", "label": "www.barebones.com", "newer": False}
        previous = {"packages": [{"name": "bbedit", "upstream": old}]}
        nothing = response("x")
        nothing.read.return_value = b"<p>Page redesigned</p>"
        for why, urlopen in (
            ("answered 404", {"side_effect": http_error(404)}),
            ("couldn't fetch", {"side_effect": urllib.error.URLError("down")}),
            ("matches", {"return_value": nothing}),
        ):
            with self.subTest(why=why), mock.patch.object(config, "RETRY_DELAYS", []):
                rows = [row("bbedit", "16.0.3", "newest", "16.0.3")]
                self.run_check(rows, urlopen, previous)
                self.assertEqual(rows[0]["upstream"]["version"], "16.0.3")
                self.assertIn(why, rows[0]["notRefreshed"]["upstream"]["reason"])
                self.assertIn(why, self.stderr.getvalue())


STEPMANIA = {"github": "stepmania/stepmania", "branch": "5_1-new"}
UNSTABLE = "5.1.0-b2-unstable-2022-11-14"


def head(since=0, until=0, date="2026-08-22T03:31:23Z"):
    """GitHub's answer for a branch: its newest commit, and how many commits
    since nixpkgs' version (and old enough to count)."""
    return {
        "oid": "825467bcd81c",
        "committedDate": date,
        "since": since,
        "until": until,
    }


class UnstableVersions(unittest.TestCase):
    def test_unstable_version(self):
        self.assertEqual(
            upstream.unstable_version(UNSTABLE, "2026-08-22T03:31:23Z"),
            "5.1.0-b2-unstable-2026-08-22",
        )
        # The date is UTC's, as in nixpkgs: 20:31 in UTC-7 is the next day.
        self.assertEqual(
            upstream.unstable_version(UNSTABLE, "2026-08-21T20:31:23-07:00"),
            "5.1.0-b2-unstable-2026-08-22",
        )
        # Never older than nixpkgs' own (another branch's commit, say).
        self.assertEqual(
            upstream.unstable_version(UNSTABLE, "2020-01-01T00:00:00Z"), UNSTABLE
        )
        self.assertIsNone(upstream.unstable_version("5.0.12", "2026-08-22T00:00:00Z"))
        self.assertIsNone(upstream.unstable_version(None, "2026-08-22T00:00:00Z"))

    def test_outdated_after(self):
        self.assertEqual(upstream.outdated_after({}), {"days": 90, "commits": None})
        self.assertEqual(
            upstream.outdated_after({"outdatedAfter": {"commits": 50}}),
            {"days": 90, "commits": 50},
        )
        self.assertEqual(
            upstream.outdated_after({"outdatedAfter": {"days": None, "commits": 5}}),
            {"days": None, "commits": 5},
        )

    def run_checks(self, check=STEPMANIA, nix=UNSTABLE, answer=None, error=None):
        rows = [row("stepmania", nix, "untrusted", "5.0.12")]
        kwargs = {"side_effect": error} if error else {"return_value": [answer]}
        with (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github, "latest_tags") as latest_tags,
            mock.patch.object(github, "branch_commits", **kwargs) as branch_commits,
        ):
            upstream.add_checks(rows, {"stepmania": check}, {"packages": []}, NOW)
        latest_tags.assert_not_called()  # no tag checks: no tag request
        return rows[0], branch_commits

    def test_query(self):
        _, branch_commits = self.run_checks(answer=head())
        # From the day after nixpkgs' commit; old enough: before 90 days ago.
        branch_commits.assert_called_once_with(
            "t",
            [
                (
                    "stepmania/stepmania",
                    "5_1-new",
                    "2022-11-15T00:00:00Z",
                    "2026-07-02T06:00:00Z",
                )
            ],
        )

    def test_outdated_once_a_commit_has_waited(self):
        r, _ = self.run_checks(answer=head(since=40, until=12))
        self.assertEqual(
            r["upstream"],
            {
                "version": "5.1.0-b2-unstable-2026-08-22",
                "newer": True,
                "behind": 40,
                "outdatedAfter": {"days": 90, "commits": None},
                "repo": "stepmania/stepmania",
                "label": "stepmania/stepmania 5_1-new branch",
                "url": "https://github.com/stepmania/stepmania/commits/5_1-new",
                "commit": "825467bcd81c",
                "checkedAt": NOW,
            },
        )
        self.assertEqual(r["refVersion"], "5.1.0-b2-unstable-2026-08-22")
        self.assertTrue(is_outdated(r))  # although Repology says untrusted

    def test_newer_commits_not_counted_yet(self):
        r, _ = self.run_checks(answer=head(since=3, until=0))
        self.assertFalse(r["upstream"]["newer"])
        self.assertEqual(r["upstream"]["behind"], 3)
        self.assertEqual(r["refVersion"], "5.0.12")  # untouched
        self.assertFalse(is_outdated(r))

    def test_enough_commits(self):
        check = {**STEPMANIA, "outdatedAfter": {"commits": 50}}
        r, _ = self.run_checks(check, answer=head(since=50, until=0))
        self.assertTrue(r["upstream"]["newer"])
        r, _ = self.run_checks(check, answer=head(since=49, until=0))
        self.assertFalse(r["upstream"]["newer"])

    def test_days_off(self):
        check = {**STEPMANIA, "outdatedAfter": {"days": None, "commits": 50}}
        r, branch_commits = self.run_checks(check, answer=head(since=10))
        self.assertIsNone(branch_commits.call_args.args[1][0][3])  # no until
        self.assertFalse(r["upstream"]["newer"])

    def test_too_recent_to_have_waited(self):
        # nixpkgs' version is from 10 days ago: no commit can have waited 90.
        _, branch_commits = self.run_checks(
            nix="5.1.0-b2-unstable-2026-09-20", answer=head()
        )
        self.assertIsNone(branch_commits.call_args.args[1][0][3])

    def test_up_to_date(self):
        r, _ = self.run_checks(answer=head(date="2022-11-14T10:00:00Z"))
        self.assertEqual(r["upstream"]["version"], UNSTABLE)
        self.assertFalse(r["upstream"]["newer"])

    def test_failures(self):
        for reason, kwargs in (
            ("GitHub request failed", {"error": urllib.error.URLError("x")}),
            ("renamed or deleted?", {"answer": None}),
            ("isn't an unstable version", {"nix": "5.0.12", "answer": head()}),
        ):
            with self.subTest(reason=reason):
                r, _ = self.run_checks(**kwargs)
                self.assertNotIn("upstream", r)  # nothing to fall back on
                self.assertIn(reason, r["notRefreshed"]["upstream"]["reason"])


class BranchCommits(unittest.TestCase):
    def test_query_and_answer(self):
        target = {
            "oid": "abc",
            "committedDate": "2026-08-22T03:31:23Z",
            "since": {"totalCount": 40},
            "until": {"totalCount": 12},
        }
        resp = response(
            {
                "data": {
                    "r0": {"ref": {"target": target}},
                    "r1": {"ref": None},  # no such branch
                }
            }
        )
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            results = github.branch_commits(
                "t",
                [
                    ("a/one", "main", "2022-11-15T00:00:00Z", "2026-07-02T06:00:00Z"),
                    ("b/two", "gone", "2022-11-15T00:00:00Z", None),
                ],
            )
        self.assertEqual(
            results,
            [
                {
                    "oid": "abc",
                    "committedDate": "2026-08-22T03:31:23Z",
                    "since": 40,
                    "until": 12,
                },
                None,
            ],
        )
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["variables"]["b0"], "refs/heads/main")
        self.assertEqual(body["variables"]["u0"], "2026-07-02T06:00:00Z")
        self.assertNotIn("u1", body["variables"])  # no until: not asked
        self.assertIn("history(since: $s0, until: $u0)", body["query"])
        self.assertNotIn("$u1", body["query"])


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
