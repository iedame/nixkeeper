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

        def counts(token, queries):
            seen.append(len(queries))
            # Encode each query in its count so misalignment would show.
            return [len(q) + ("is:issue" in q) for q in queries]

        with mock.patch.object(config, "GITHUB_SEARCH_BATCH", 4), \
             mock.patch.object(github, "token", return_value="t"), \
             mock.patch.object(github, "search_counts", side_effect=counts):
            github.add_counts(rows)
        self.assertEqual(seen, [4, 2])
        for row in rows:
            pr = f"repo:NixOS/nixpkgs is:pr state:open in:title {row['searchTerm']}"
            issue = f"repo:NixOS/nixpkgs is:issue state:open in:title {row['searchTerm']}"
            self.assertEqual((row["openPRs"], row["openIssues"]), (len(pr), len(issue) + 1))

    def test_no_token_skips_counts(self):
        rows = [{"searchTerm": "a"}]
        with mock.patch.object(github, "token", return_value=None):
            github.add_counts(rows)
        self.assertNotIn("openPRs", rows[0])

    def test_partial_graphql_answer(self):
        resp = response({"data": {"s0": {"issueCount": 3}, "s1": None}, "errors": [{"message": "s1 failed"}]})
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(github.search_counts("t", ["q0", "q1"]), [3, None])

    def test_failed_request_blanks_its_batch(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(401)):
            self.assertEqual(github.search_counts("t", ["q0", "q1"]), [None, None])
