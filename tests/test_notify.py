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

    def test_build_failure_links_its_log(self):
        row = {
            "name": "ac-library",
            "nixStatus": "newest",
            "builds": [
                {
                    "attr": "ac-library",
                    "system": "aarch64-darwin",
                    "status": "failed",
                    "build": 345227373,
                }
            ],
        }
        self.assertEqual(
            notify.describe(row, NOW),
            "`ac-library` — build failure on aarch64-darwin · [aarch64-darwin log]"
            "(https://hydra.nixos.org/build/345227373/log)",
        )

    def test_outdated_by_update_check(self):
        row = {
            "name": "wesnoth-devel",
            "nixStatus": "devel",
            "nixVersion": "1.19.24",
            "refVersion": "1.19.28",
            "upstream": {"version": "1.19.28", "newer": True},
            "outdatedSince": NOW,
        }
        self.assertEqual(
            notify.describe(row, NOW),
            "`wesnoth-devel` 1.19.24 → 1.19.28 (found by nixkeeper's update check)"
            " · outdated today",
        )

    def test_vulnerable_links_known_cves(self):
        row = {
            "name": "python313Packages.requests",
            "nixStatus": "newest",
            "project": "python:requests",
            "nixVulnerable": True,
        }
        self.assertEqual(
            notify.describe(row, NOW),
            "`python313Packages.requests` — flagged vulnerable ([known CVEs]"
            "(https://repology.org/project/python%3Arequests/cves))",
        )
        body = notify.status_body([row], diff({"packages": []}, [row]), NOW)
        self.assertIn(
            "### Flagged vulnerable (1)\n- `python313Packages.requests`", body
        )

    def test_not_refreshed_says_what_and_why(self):
        row = {
            "name": "bbedit",
            "nixStatus": "newest",
            "notRefreshed": {
                "upstream": {
                    "since": "2026-09-30T06:00:00+00:00",
                    "reason": "https://example.org answered 404 (moved?)",
                }
            },
        }
        self.assertEqual(
            notify.describe(row, NOW),
            "`bbedit` — nixkeeper's update check failing "
            "(package-lists/update-checks.nix) since 2026-09-30: "
            "https://example.org answered 404 (moved?)",
        )
        body = notify.status_body([row], diff({"packages": []}, [row]), NOW)
        self.assertIn("### Not refreshed (1)", body)

    def test_waiting_for_channel(self):
        row = {
            "name": "wesnoth-devel",
            "nixStatus": "outdated",
            "nixVersion": "1.19.24",
            "refVersion": "1.19.28",
            "master": "1.19.28",
            "outdatedSince": NOW,
        }
        self.assertEqual(
            notify.describe(row, NOW),
            "`wesnoth-devel` 1.19.24 → 1.19.28 · outdated today"
            " · on master (1.19.28), waiting for nixos-unstable",
        )

    def test_update_prs(self):
        url = "https://github.com/NixOS/nixpkgs/pull/"
        outdated = {
            "name": "google-chrome",
            "nixStatus": "outdated",
            "nixVersion": "1",
            "refVersion": "2",
            "openPR": {"number": 7, "url": f"{url}7", "draft": False},
        }
        self.assertTrue(
            notify.describe(outdated, NOW).endswith(f" · PR [#7]({url}7) open")
        )
        waiting = {
            **outdated,
            "master": "2",
            "masterPR": {"number": 6, "url": f"{url}6"},
        }
        self.assertTrue(
            notify.describe(waiting, NOW).endswith(
                f" · on master (2), waiting for nixos-unstable ([#6]({url}6))"
            )
        )

    def test_update_failure_links_its_log(self):
        log = "https://nixpkgs-update-logs.nixos.org/egoboo/2026-09-15.log"
        row = {
            "name": "egoboo",
            "nixStatus": "newest",
            "updateFailure": True,
            "update": {"attr": "egoboo", "date": "2026-09-15", "log": log},
        }
        self.assertEqual(
            notify.describe(row, NOW),
            f"`egoboo` — update failure reported · [update log]({log})",
        )

    def test_marked_broken(self):
        row = {
            "name": "libfilezilla",
            "nixStatus": "newest",
            "builds": [
                {"attr": "libfilezilla", "system": "x86_64-linux", "status": "ok"},
                {
                    "attr": "libfilezilla",
                    "system": "aarch64-darwin",
                    "status": "broken",
                },
            ],
        }
        body = notify.status_body([row], diff({"packages": []}, [row]), NOW)
        self.assertIn(
            "### Marked broken in nixpkgs (1)\n- `libfilezilla` — marked broken in "
            "nixpkgs on aarch64-darwin",
            body,
        )
        self.assertNotIn("### Failed", body)

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


class Subscribers(unittest.TestCase):
    """Status issues of their own, for maintainers and teams (notifications/)."""

    ME = {"maintainer": "iedame"}
    GAMING = {"team": "Gaming", "mention": ["iedame"]}
    EVERYONE = [
        {
            "name": "unciv",
            "nixStatus": "outdated",
            "nixVersion": "4.22.1",
            "refVersion": "4.22.4",
            "maintainers": ["IEdame"],
        },
        {
            "name": "egoboo",
            "nixStatus": "newest",
            "nixVersion": "2.8.1",
            "teams": ["Gaming"],
            "teamsByList": ["Gaming"],
        },
        {
            "name": "openttd",
            "nixStatus": "newest",
            "nixVersion": "14.1",
            "teams": ["Gaming"],
            "maintainers": ["iedame"],
        },
        {
            "name": "rPackages.foo",
            "nixStatus": "outdated",
            "nixVersion": "1",
            "set": "rPackages",
            "maintainers": ["iedame"],
        },
        {
            "name": "other",
            "nixStatus": "newest",
            "nixVersion": "1",
            "maintainers": ["x"],
        },
    ]

    def setUp(self):
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch.object(notify.time, "sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_whose_packages(self):
        mine = [r["name"] for r in self.EVERYONE if notify.is_subscribed(self.ME, r)]
        team = [
            r["name"] for r in self.EVERYONE if notify.is_subscribed(self.GAMING, r)
        ]
        # Any case; not the sets updated in bulk; a list's team counts too.
        self.assertEqual(mine, ["unciv", "openttd"])
        self.assertEqual(team, ["egoboo", "openttd"])
        self.assertEqual(notify.mentions(self.GAMING), ["iedame"])
        self.assertEqual(
            notify.subscriber_title(self.GAMING), "nixkeeper status: Gaming team"
        )
        self.assertEqual(
            notify.subscriber_page("https://nixkeeper.com", self.ME),
            "https://nixkeeper.com/?q=%40iedame",
        )

    def fake_github(self, open_issues):
        calls = []

        def api(method, path, token, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return open_issues
            if method == "POST" and path.endswith("/issues"):
                return {"number": 40}
            return None

        return mock.patch.object(github, "api", side_effect=api), calls

    def test_issues_written_opened_and_closed(self):
        existing = [
            {"number": 3, "title": "nixkeeper status: @iedame"},
            {"number": 9, "title": "nixkeeper status: someone-gone"},
        ]
        patched, calls = self.fake_github(existing)
        before = {"packages": [{**r, "nixStatus": "newest"} for r in self.EVERYONE]}
        with patched:
            notify.subscriber_issues(
                "o/r",
                "t",
                {"maintainers/iedame": self.ME, "teams/gaming": self.GAMING},
                before,
                self.EVERYONE,
                NOW,
            )
        writes = [(m, p) for m, p, _ in calls if m != "GET"]
        self.assertIn(("PATCH", "/repos/o/r/issues/3"), writes)  # iedame's, rewritten
        self.assertIn(("POST", "/repos/o/r/issues"), writes)  # Gaming's, opened
        # unciv newly outdated: iedame's issue gets a comment; Gaming's doesn't.
        self.assertIn(("POST", "/repos/o/r/issues/3/comments"), writes)
        self.assertNotIn(("POST", "/repos/o/r/issues/40/comments"), writes)
        # Its file gone: commented and closed.
        self.assertIn(("POST", "/repos/o/r/issues/9/comments"), writes)
        self.assertIn(("PATCH", "/repos/o/r/issues/9"), writes)
        opened = next(
            b for m, p, b in calls if m == "POST" and p == "/repos/o/r/issues"
        )
        self.assertEqual(opened["title"], "nixkeeper status: Gaming team")
        self.assertEqual(notify.subscriber_title(self.ME), "nixkeeper status: @iedame")
        self.assertIn("@iedame", opened["body"])  # mentioned: subscribed
        self.assertIn("2 packages tracked", opened["body"])

    def test_status_issue_turned_off(self):
        patched, calls = self.fake_github([{"number": 1, "title": "nixkeeper status"}])
        env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t"}
        with (
            patched,
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(github, "update_status_issue") as update,
        ):
            notify.github_issue(
                ROWS, diff(BEFORE, ROWS), NOW, lists={"statusIssue": False}
            )
        update.assert_not_called()
        self.assertIn(("PATCH", "/repos/o/r/issues/1", {"state": "closed"}), calls)

    def test_malformed_files_left_out(self):
        read = {
            "maintainers": {
                "iedame": {"maintainer": "iedame"},
                "both": {"maintainer": "a", "team": "b"},
                "a-team": {"team": "Gaming"},  # in the wrong folder
            },
            "teams": {
                "gaming": {"team": "Gaming", "mention": ["iedame"]},
                "nothing": {},
                "badmention": {"team": "Gaming", "mention": "iedame"},
            },
        }
        exists = mock.patch.object(notify.os.path, "exists", return_value=True)
        with (
            exists,
            mock.patch.object(notify.nixpkgs_source, "read_lists", return_value=read),
        ):
            self.assertEqual(
                notify.read_subscribers("x"),
                {
                    "maintainers/iedame": {"maintainer": "iedame"},
                    "teams/gaming": {"team": "Gaming", "mention": ["iedame"]},
                },
            )
        with (
            exists,
            mock.patch.object(
                notify.nixpkgs_source, "read_lists", side_effect=SystemExit("no eval")
            ),
        ):
            self.assertEqual(notify.read_subscribers("x"), {})  # the sync goes on
