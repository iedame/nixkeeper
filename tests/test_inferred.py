import io
import re
import unittest
from unittest import mock

from nixkeeper import inferred
from nixkeeper.sources import github
from nixkeeper.sources import nixpkgs as nixpkgs_source


def src(version, **fields):
    return {"version": version, **fields}


class GithubCheck(unittest.TestCase):
    def check(self, source):
        return inferred.github_check(source)

    def test_tag_is_the_version(self):
        check, _ = self.check(
            src(
                "1.19.28",
                gitRepoUrl="https://github.com/wesnoth/wesnoth.git",
                tag="1.19.28",
            )
        )
        self.assertEqual(check["github"], "wesnoth/wesnoth")
        self.assertEqual(check["tags"], r"^([0-9]+(?:[\.][0-9]+)*)$")

    def test_prefix_from_the_tag(self):
        check, _ = self.check(
            src(
                "2.34.2",
                gitRepoUrl="https://github.com/psf/requests.git",
                rev="refs/tags/v2.34.2",
            )
        )
        regex = re.compile(check["tags"])
        self.assertEqual(regex.search("v2.35.0").group(1), "2.35.0")
        # Pre-releases, other schemes and other prefixes don't count.
        for tag in ("v2.35.0rc1", "2.35.0", "v2_35_0", "release-2.35.0"):
            self.assertIsNone(regex.search(tag), tag)

    def test_from_a_download_url(self):
        release, _ = self.check(
            src(
                "0.7.2",
                url="https://github.com/a/b/releases/download/v0.7.2/b-0.7.2.tar.gz",
            )
        )
        archive, _ = self.check(
            src("3.0", url="https://github.com/a/b/archive/refs/tags/release-3.0.zip")
        )
        self.assertEqual(
            release, {"github": "a/b", "tags": r"^v([0-9]+(?:[\.][0-9]+)*)$"}
        )
        self.assertEqual(archive["tags"], r"^release\-([0-9]+(?:[\.][0-9]+)*)$")

    def test_separators_follow_the_version(self):
        check, _ = self.check(
            src("7_2", gitRepoUrl="https://github.com/a/b.git", tag="R7_2")
        )
        self.assertEqual(re.search(check["tags"], "R7_3").group(1), "7_3")
        self.assertIsNone(re.search(check["tags"], "R7.3"))

    def test_not_worked_out(self):
        gh = "https://github.com/a/b.git"
        cases = {
            "not from GitHub": src(
                "1.0", gitRepoUrl="https://gitlab.com/a/b.git", tag="1.0"
            ),
            "no tag": src("1.0", url="https://github.com/a/b/raw/main/x"),
            "a commit (unstable version)": src(
                "0-unstable-2024-05-01", gitRepoUrl=gh, rev="a" * 40
            ),
            "not a plain version": src("1.0-beta2", gitRepoUrl=gh, tag="v1.0-beta2"),
            "tag doesn't end with the version": src(
                "3.2.6", gitRepoUrl=gh, tag="R3_2_6"
            ),
        }
        for why, source in cases.items():
            self.assertEqual(self.check(source), (None, why), why)

    def test_first_attribute_that_gives_one(self):
        sources = {
            "heroic": src("2.18.1"),
            "heroic-unwrapped": src(
                "2.18.1", gitRepoUrl="https://github.com/H/heroic.git", tag="v2.18.1"
            ),
        }
        row = {"name": "heroic", "attrs": ["heroic", "heroic-unwrapped"]}
        check, _ = inferred.for_row(row, sources)
        self.assertEqual(check["github"], "H/heroic")
        self.assertEqual(
            inferred.for_row({"name": "x", "attrs": ["x"]}, {}), (None, "no source")
        )


class Verdict(unittest.TestCase):
    def test_against_repology(self):
        def v(version, status="newest", ref=None):
            row = {"nixVersion": "1.0", "nixStatus": status, "refVersion": ref}
            return inferred.verdict(row, version, rule=False)

        self.assertEqual(v("1.0"), ("agree", "up to date"))
        self.assertEqual(v("1.1", "outdated", "1.1"), ("agree", "outdated, 1.1"))
        self.assertEqual(v("1.1"), ("disagree", "GitHub 1.1, Repology up to date"))
        self.assertEqual(
            v("1.0", "outdated", "1.2"), ("disagree", "Repology 1.2, GitHub 1.0")
        )
        self.assertEqual(
            v("1.1", "legacy", "1.2"),
            ("disagree", "both outdated: GitHub 1.1, Repology 1.2"),
        )

    def test_against_its_own_rule(self):
        row = {"nixVersion": "1.0", "upstream": {"version": "1.2"}}
        self.assertEqual(
            inferred.verdict(row, "1.2", rule=True), ("agree", "1.2, as its rule")
        )
        self.assertEqual(
            inferred.verdict(row, "1.3", rule=True),
            ("disagree", "1.3, its rule 1.2"),
        )


class Compare(unittest.TestCase):
    ROWS = [
        {"name": "a", "attrs": ["a"], "nixVersion": "1.0", "nixStatus": "newest"},
        {"name": "b", "attrs": ["b"], "nixVersion": "2.0", "nixStatus": "newest"},
        {"name": "c", "attrs": ["c"], "nixVersion": "3.0", "nixStatus": "newest"},
        {"name": "d", "attrs": ["d"], "nixVersion": "1.0", "nixStatus": "newest"},
        {"name": "gone", "attrs": ["gone"], "nixStatus": "missing"},
    ]
    SOURCES = {
        "a": src("1.0", gitRepoUrl="https://github.com/o/a.git", tag="v1.0"),
        "b": src("2.0", gitRepoUrl="https://github.com/o/b.git", tag="2.0"),
        "c": src("3.0", url="https://example.org/c-3.0.tar.gz"),
        "d": src("1.0", gitRepoUrl="https://github.com/o/d.git", tag="1.0"),
    }

    def compare(self, checks=None, token="t", sources=None, tags=None):
        out = io.StringIO()
        with (
            mock.patch("sys.stderr", out),
            mock.patch.object(github, "token", return_value=token),
            mock.patch.object(
                nixpkgs_source, "sources", **(sources or {"return_value": self.SOURCES})
            ) as get_sources,
            mock.patch.object(
                github,
                "latest_tags",
                return_value=tags or {"o/a": ["v1.0", "v1.1rc1"], "o/b": ["2.1"]},
            ) as latest_tags,
        ):
            rows = [dict(r) for r in self.ROWS]
            inferred.compare(rows, checks or {}, "abc123")
        self.assertEqual(rows, self.ROWS)  # changes no row
        return out.getvalue(), get_sources, latest_tags

    def test_logs_how_they_compare(self):
        out, get_sources, latest_tags = self.compare()
        # Packages nixpkgs doesn't have aren't evaluated.
        get_sources.assert_called_once_with({"a", "b", "c", "d"}, "abc123")
        latest_tags.assert_called_once_with("t", ["o/a", "o/b", "o/d"])
        self.assertIn(
            "::group::Worked-out update checks (not used yet): 3 of 4 packages, "
            "1 agree with Repology or their rule, 1 don't, 1 failed",
            out,
        )
        self.assertIn("Not worked out: 1 not from GitHub", out)
        self.assertIn("  b 2.0: GitHub 2.1, Repology up to date  (o/b)", out)
        self.assertIn("  a 1.0: up to date  (o/a)", out)
        self.assertIn("  d: couldn't read the tags of o/d", out)
        self.assertTrue(out.rstrip().endswith("::endgroup::"))

    def test_follows_is_left_out(self):
        out, _, latest_tags = self.compare(checks={"b": {"follows": "a"}})
        latest_tags.assert_called_once_with("t", ["o/a", "o/d"])
        self.assertIn("2 of 4 packages", out)

    def test_skipped_without_a_token_or_an_evaluation(self):
        out, get_sources, _ = self.compare(token=None)
        get_sources.assert_not_called()
        self.assertEqual(out, "Worked-out update checks: skipped (no GITHUB_TOKEN)\n")
        error = nixpkgs_source.EvalError("error: boom")
        out, _, latest_tags = self.compare(sources={"side_effect": error})
        latest_tags.assert_not_called()
        self.assertEqual(out, "Worked-out update checks: skipped (error: boom)\n")
