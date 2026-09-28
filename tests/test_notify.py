import io
import os
import unittest
import urllib.error
from unittest import mock

from nixkeeper import notify
from nixkeeper.changes import diff
from nixkeeper.sources import github
from tests.helpers import http_error

NOW = "2026-09-28T06:00:00+00:00"
BEFORE = {
    "packages": [
        {"name": "unciv", "nixStatus": "newest", "nixVersion": "4.22.4"},
        {"name": "xournalpp", "nixStatus": "outdated", "nixVersion": "1.3.7"},
    ]
}
ROWS = [
    {
        "name": "unciv",
        "nixStatus": "outdated",
        "nixVersion": "4.22.1",
        "refVersion": "4.22.4",
        "outdatedSince": "2026-09-25T06:00:00+00:00",
    },
    {"name": "xournalpp", "nixStatus": "newest", "nixVersion": "1.3.8"},
    {"name": "fzssh", "nixStatus": "missing", "nixVersion": None},
]


class Text(unittest.TestCase):
    def test_status_body(self):
        body = notify.status_body(
            ROWS, diff(BEFORE, ROWS), NOW, "https://iedame.github.io/nixkeeper/"
        )
        self.assertIn("3 packages tracked", body)
        self.assertIn("### Failed (1)\n- `fzssh` — not in nixpkgs", body)
        self.assertIn(
            "### Outdated (1)\n- `unciv` 4.22.1 → 4.22.4 · outdated 3 days", body
        )
        self.assertIn("**Caught up:** `xournalpp`", body)  # quiet changes still listed
        self.assertIn("**Now tracked:** `fzssh`", body)

    def test_nothing_to_report(self):
        rows = [{"name": "a", "nixStatus": "newest"}]
        body = notify.status_body(rows, diff({"packages": rows}, rows), NOW)
        self.assertIn("Nothing needs attention.", body)
        self.assertIn("No changes.", body)

    def test_comment_lists_only_notifying_changes(self):
        comment = notify.change_comment(diff(BEFORE, ROWS), NOW)
        self.assertIn(
            "**Newly outdated:** `unciv` 4.22.1 → 4.22.4 · outdated 3 days", comment
        )
        self.assertNotIn("xournalpp", comment)  # caught up: quiet
        self.assertNotIn("fzssh", comment)  # newly tracked: quiet

    def test_days_text(self):
        self.assertEqual(notify.days_text("2026-09-28T01:00:00+00:00", NOW), "today")
        self.assertEqual(notify.days_text("2026-09-27T06:00:00+00:00", NOW), "1 day")
        self.assertEqual(notify.days_text("2026-08-29T06:00:00+00:00", NOW), "30 days")


class Posting(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        self.stderr = patcher.start()
        self.addCleanup(patcher.stop)

    def run_notify(self, env, before=BEFORE, rows=ROWS):
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(github, "update_status_issue", return_value=7) as update,
        ):
            notify.notify(before, rows, NOW)
        return update

    def test_local_runs_never_post(self):
        self.run_notify(
            {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "iedame/nixkeeper"}
        ).assert_not_called()

    def test_ci_posts_body_and_comment(self):
        update = self.run_notify(
            {
                "NIXKEEPER_NOTIFY": "1",
                "GITHUB_TOKEN": "t",
                "GITHUB_REPOSITORY": "iedame/nixkeeper",
            }
        )
        repo, token, title, body, comment = update.call_args.args
        self.assertEqual(
            (repo, token, title), ("iedame/nixkeeper", "t", "nixkeeper status")
        )
        self.assertIn("https://iedame.github.io/nixkeeper/", body)
        self.assertIn("Newly outdated", comment)

    def test_no_comment_when_nothing_new(self):
        update = self.run_notify(
            {"NIXKEEPER_NOTIFY": "1", "GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"},
            before={"packages": ROWS},
        )
        self.assertIsNone(update.call_args.args[4])

    def test_failure_is_a_warning_not_a_crash(self):
        with (
            mock.patch.dict(
                os.environ,
                {
                    "NIXKEEPER_NOTIFY": "1",
                    "GITHUB_TOKEN": "t",
                    "GITHUB_REPOSITORY": "o/r",
                },
            ),
            mock.patch.object(
                github, "update_status_issue", side_effect=urllib.error.URLError("down")
            ),
        ):
            notify.notify(BEFORE, ROWS, NOW)
        self.assertIn("::warning::", self.stderr.getvalue())


class StatusIssue(unittest.TestCase):
    """github.update_status_issue against a fake REST API."""

    def fake_api(self, open_issues, label_exists=True):
        calls = []

        def api(method, path, token, body=None):
            calls.append((method, path.split("?")[0], body))
            if path.endswith("/labels"):
                if label_exists:
                    raise http_error(422)
                return {}
            if method == "GET":
                return open_issues
            if method == "POST" and path.endswith("/issues"):
                return {"number": 12}
            return {}

        return calls, api

    def test_rewrites_existing_issue_and_comments(self):
        calls, api = self.fake_api([{"number": 5}])
        with mock.patch.object(github, "api", side_effect=api):
            self.assertEqual(
                github.update_status_issue("o/r", "t", "title", "body", "news"), 5
            )
        self.assertIn(("PATCH", "/repos/o/r/issues/5", {"body": "body"}), calls)
        self.assertIn(("POST", "/repos/o/r/issues/5/comments", {"body": "news"}), calls)

    def test_opens_issue_when_none_is_open(self):
        calls, api = self.fake_api([], label_exists=False)
        with mock.patch.object(github, "api", side_effect=api):
            self.assertEqual(
                github.update_status_issue("o/r", "t", "title", "body"), 12
            )
        self.assertIn(
            (
                "POST",
                "/repos/o/r/issues",
                {"title": "title", "body": "body", "labels": ["nixkeeper-status"]},
            ),
            calls,
        )
        self.assertFalse(any(path.endswith("/comments") for _, path, _ in calls))

    def test_other_label_errors_propagate(self):
        def api(method, path, token, body=None):
            raise http_error(403)

        with (
            mock.patch.object(github, "api", side_effect=api),
            self.assertRaises(urllib.error.HTTPError) as raised,
        ):
            github.update_status_issue("o/r", "t", "title", "body")
        raised.exception.close()  # else Python warns about the unclosed error
