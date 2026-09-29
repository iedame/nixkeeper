import io
import json
import os
import tempfile
import unittest
from unittest import mock

from nixkeeper import notify, prcheck
from nixkeeper.sources import github

URL = "https://github.com/NixOS/nixpkgs/pull/"


def pr(number, title, base="master", draft=False):
    """A pull request as the GitHub search returns it."""
    return {
        "number": number,
        "title": title,
        "url": f"{URL}{number}",
        "isDraft": draft,
        "baseRefName": base,
    }


def row(name, status="outdated", **extra):
    return {
        "name": name,
        "searchTerm": name,
        "nixStatus": status,
        "nixVersion": "1.19.24",
        "refVersion": "1.19.28",
        **extra,
    }


class PRCheck(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        cwd = os.getcwd()
        os.chdir(self.dir.name)
        self.addCleanup(os.chdir, cwd)
        os.mkdir("data")
        self.stderr = io.StringIO()
        patcher = mock.patch("sys.stderr", self.stderr)
        patcher.start()
        self.addCleanup(patcher.stop)

    def publish(self, *rows):
        index = {"checkedAt": "2026-09-30T06:00:00+00:00", "packages": list(rows)}
        with open("data/index.json", "w") as f:
            json.dump(index, f)
        return index

    def run_check(self, answers):
        """prcheck.main() with GitHub answering {query part: [pull requests]}."""
        searched = []

        def search_batch(token, searches):
            searched.extend(q for q, _ in searches)
            return [
                next((1, prs) for key, prs in answers.items() if key in q)
                for q, _ in searches
            ]

        with (
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github, "search_batch", side_effect=search_batch),
            mock.patch.object(notify, "notify") as notified,
        ):
            prcheck.main()
        with open("data/index.json") as f:
            return json.load(f), notified, searched

    def test_open_and_merged_update_prs(self):
        self.publish(
            row("wesnoth-devel"),
            row("unciv"),
            row("backrest", "newest"),  # not outdated: not searched
        )
        index, notified, searched = self.run_check(
            {
                "in:title wesnoth-devel": [],
                "state:open in:title unciv": [pr(7, "unciv: 4.22.1 -> 4.22.5")],
                "is:merged in:title unciv": [],
            }
        )
        wesnoth, unciv, _ = index["packages"]
        self.assertEqual(unciv["openPR"]["number"], 7)
        self.assertNotIn("openPR", wesnoth)
        self.assertFalse(any("backrest" in q for q in searched))
        notified.assert_called_once()

    def test_merged_into_master_is_on_master_before_hydra(self):
        self.publish(row("wesnoth-devel"))
        index, _, _ = self.run_check(
            {
                "state:open": [],
                "is:merged": [
                    # Into staging: weeks from master, so not "on master".
                    pr(8, "wesnoth-devel: 1.19.24 -> 1.19.30", base="staging"),
                    pr(6, "wesnoth-devel: 1.19.24 -> 1.19.28"),
                    pr(5, "wesnoth-devel: 1.19.22 -> 1.19.24"),  # already in
                ],
            }
        )
        [wesnoth] = index["packages"]
        self.assertEqual(wesnoth["masterPR"]["number"], 6)
        self.assertNotIn("master", wesnoth)  # Hydra hasn't built it: no matter

    def test_merged_pr_supersedes_the_bots_failure(self):
        failed = {
            "attr": "wesnoth-devel",
            "date": "2026-09-22",
            "outcome": "failed",
            "was": "wesnoth-devel-1.19.24",
        }
        self.publish(row("wesnoth-devel", update=failed, updateFailure=True))
        index, _, _ = self.run_check(
            {
                "state:open": [],
                "is:merged": [pr(6, "wesnoth-devel: 1.19.24 -> 1.19.28")],
            }
        )
        [wesnoth] = index["packages"]
        self.assertFalse(wesnoth["updateFailure"])
        self.assertEqual(
            (wesnoth["update"]["outcome"], wesnoth["update"]["supersededOn"]),
            ("superseded", "master"),
        )

    def test_nothing_changed_writes_nothing(self):
        existing = {
            "number": 7,
            "title": "unciv: 4.22.1 -> 4.22.5",
            "url": f"{URL}7",
            "draft": False,
            "base": "master",
            "from": "4.22.1",
            "to": "4.22.5",
        }
        before = self.publish(row("unciv", nixVersion="4.22.1", openPR=existing))
        index, notified, _ = self.run_check(
            {"state:open": [pr(7, "unciv: 4.22.1 -> 4.22.5")], "is:merged": []}
        )
        self.assertEqual(index, before)
        notified.assert_not_called()

    def test_failed_search_keeps_what_was_there(self):
        existing = {"number": 7, "to": "1.19.28", "url": f"{URL}7", "draft": False}
        self.publish(row("wesnoth-devel", openPR=existing))
        with (
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(
                github, "search_batch", side_effect=lambda t, s: [(None, [])] * len(s)
            ),
            mock.patch.object(notify, "notify"),
        ):
            prcheck.main()
        with open("data/index.json") as f:
            self.assertEqual(json.load(f)["packages"][0]["openPR"], existing)
