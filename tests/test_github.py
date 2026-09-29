import io
import unittest
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import github
from tests.helpers import http_error, response


class GitHubCounts(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_counts_line_up_with_rows_across_batches(self):
        rows = [{"searchTerm": t} for t in ("a", "b", "c")]
        seen = []

        def search_batch(token, searches):
            seen.append(len(searches))
            # Encode each query in its count so misalignment would show.
            return [(len(q) + ("is:issue" in q), []) for q, _ in searches]

        with (
            mock.patch.object(config, "GITHUB_SEARCH_BATCH", 4),
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github, "search_batch", side_effect=search_batch),
        ):
            github.add_counts(rows)
        self.assertEqual(seen, [4, 2])
        for row in rows:
            term = f"in:title {row['searchTerm']} sort:updated-desc"
            pr = f"repo:NixOS/nixpkgs is:pr state:open {term}"
            issue = f"repo:NixOS/nixpkgs is:issue state:open {term}"
            self.assertEqual(
                (row["openPRs"], row["openIssues"]), (len(pr), len(issue) + 1)
            )

    def test_no_token_skips_counts(self):
        rows = [{"searchTerm": "a"}]
        with mock.patch.object(github, "token", return_value=None):
            github.add_counts(rows)
        self.assertNotIn("openPRs", rows[0])

    def test_partial_graphql_answer(self):
        resp = response(
            {
                "data": {"s0": {"issueCount": 3}, "s1": None},
                "errors": [{"message": "s1 failed"}],
            }
        )
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(github.search_counts("t", ["q0", "q1"]), [3, None])

    def test_failed_request_blanks_its_batch(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(401)):
            self.assertEqual(github.search_counts("t", ["q0", "q1"]), [None, None])


class CountWarnings(unittest.TestCase):
    @staticmethod
    def rows(*counts):
        return [
            {"searchTerm": str(i), "openPRs": p, "openIssues": i_}
            for i, (p, i_) in enumerate(counts)
        ]

    def test_prs_mirroring_issues_warns(self):
        [warning] = github.count_warnings(
            self.rows((5, 5), (1, 1), (0, 0), (0, 0), (2, 2))
        )
        self.assertIn("pull-requests: read", warning)

    def test_real_looking_counts_dont_warn(self):
        # 17 of 28 were equal in real data (mostly 0/0): only *all* equal is suspicious.
        self.assertEqual(
            github.count_warnings(self.rows((1, 5), (1, 1), (0, 0), (0, 0), (1, 0))), []
        )

    def test_all_zero_or_too_few_rows_dont_warn(self):
        self.assertEqual(github.count_warnings(self.rows(*[(0, 0)] * 10)), [])
        self.assertEqual(github.count_warnings(self.rows((3, 3), (1, 1))), [])

    def test_failed_searches_warn(self):
        [warning] = github.count_warnings(self.rows((1, None), (None, None), (0, 0)))
        self.assertIn("3 of 6", warning)

    def test_add_counts_prints_warnings(self):
        rows = [{"searchTerm": t} for t in "abcde"]
        stderr = io.StringIO()
        with (
            mock.patch("sys.stderr", stderr),
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(
                github, "search_batch", side_effect=lambda tok, s: [(2, [])] * len(s)
            ),
        ):
            github.add_counts(rows)
        self.assertIn(
            "::warning::every package's open PR count equals", stderr.getvalue()
        )


def pr(number, title, draft=False, base="master"):
    """A pull request as the GitHub search returns it."""
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/NixOS/nixpkgs/pull/{number}",
        "isDraft": draft,
        "baseRefName": base,
    }


class UpdatePRs(unittest.TestCase):
    ROW = {"searchTerm": "wesnoth-devel", "nixVersion": "1.19.24"}

    def test_only_this_packages_update_prs(self):
        nodes = [
            pr(1, "wesnoth-devel: 1.19.24 -> 1.19.28"),
            pr(2, "wesnoth-devel-extra: 1.0 -> 1.1"),  # another package
            pr(3, "wesnoth-devel: fix build on darwin"),  # not an update
            pr(4, "treewide: bump wesnoth-devel and friends"),
        ]
        self.assertEqual(
            [p["number"] for p in github.update_prs(nodes, "wesnoth-devel")], [1]
        )

    def test_open_update_pr_aims_highest_ready_first(self):
        nodes = [
            pr(1, "wesnoth-devel: 1.19.24 -> 1.19.26"),
            pr(2, "wesnoth-devel: 1.19.24 -> 1.19.28", draft=True),
            pr(3, "wesnoth-devel: 1.19.24 -> 1.19.28"),
            pr(4, "wesnoth-devel: 1.19.20 -> 1.19.22"),  # older than nixpkgs: stale
        ]
        found = github.open_update_pr(self.ROW, nodes)
        self.assertEqual(
            (found["number"], found["to"], found["draft"]), (3, "1.19.28", False)
        )
        self.assertIsNone(github.open_update_pr(self.ROW, [nodes[3]]))

    def test_merged_update_pr_into_master_only(self):
        nodes = [
            pr(5, "wesnoth-devel: 1.19.22 -> 1.19.24"),  # already in the channel
            pr(6, "wesnoth-devel: 1.19.24 -> 1.19.28"),
            pr(8, "wesnoth-devel: 1.19.24 -> 1.19.30", base="staging"),
        ]
        self.assertEqual(github.merged_update_pr(self.ROW, nodes)["number"], 6)
        self.assertIsNone(github.merged_update_pr(self.ROW, [nodes[0], nodes[2]]))

    def test_add_counts_finds_them(self):
        row = {**self.ROW, "master": "1.19.28", "openPR": {"number": 0}}
        answers = {
            "is:pr state:open": (1, [pr(7, "wesnoth-devel: 1.19.24 -> 1.19.30")]),
            "is:issue": (0, []),
            "is:merged": (9, [pr(6, "wesnoth-devel: 1.19.24 -> 1.19.28")]),
        }

        def search_batch(token, searches):
            return [
                next(a for key, a in answers.items() if key in q) for q, _ in searches
            ]

        with (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github, "search_batch", side_effect=search_batch),
        ):
            github.add_counts([row])
        self.assertEqual((row["openPRs"], row["openIssues"]), (1, 0))
        self.assertEqual(row["openPR"]["number"], 7)  # replaced, not kept
        self.assertNotIn("masterPR", row)  # add_update_prs' job

    def test_add_update_prs(self):
        row = {**self.ROW}
        answers = {
            "is:pr state:open": (1, [pr(7, "wesnoth-devel: 1.19.24 -> 1.19.30")]),
            "is:merged": (9, [pr(6, "wesnoth-devel: 1.19.24 -> 1.19.28")]),
        }
        searched = []

        def search_batch(token, searches):
            searched.extend(q for q, _ in searches)
            return [
                next(a for key, a in answers.items() if key in q) for q, _ in searches
            ]

        with (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github, "search_batch", side_effect=search_batch),
        ):
            github.add_update_prs([row])
            self.assertEqual(
                (row["openPR"]["number"], row["masterPR"]["number"]), (7, 6)
            )
            searched.clear()
            github.add_update_prs([row], open_prs=False)  # after add_counts
        self.assertEqual(len(searched), 1)
        self.assertIn("is:merged", searched[0])

    def test_search_batch_returns_pull_requests(self):
        resp = response(
            {
                "data": {
                    "s0": {"issueCount": 2, "nodes": [pr(1, "a: 1 -> 2"), {}]},
                    "s1": {"issueCount": 5},
                }
            }
        )
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            results = github.search_batch("t", [("q0", 20), ("q1", 0)])
        self.assertEqual(results, [(2, [pr(1, "a: 1 -> 2")]), (5, [])])
        query = urlopen.call_args.args[0].data.decode()
        self.assertIn("first: 20", query)
        self.assertIn("isDraft", query)
