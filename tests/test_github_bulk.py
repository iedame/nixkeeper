import io
import unittest
from unittest import mock

from nixkeeper.sources import github, github_bulk


def pr(number, title, base="master", draft=False):
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/NixOS/nixpkgs/pull/{number}",
        "isDraft": draft,
        "baseRefName": base,
    }


PRS = [
    pr(1, "wine: 10.15 -> 10.16"),
    pr(2, "winetricks: 20250102 -> 20260125"),
    pr(3, "wesnoth-devel: 1.19.24 -> 1.19.28", draft=True),
    pr(4, "wesnoth-devel: 1.19.24 -> 1.19.29"),
    pr(5, "python3Packages.requests: 2.34.2 -> 2.35.0", base="staging"),
    pr(6, "treewide: drop Wine 9 from games"),
    # GitHub's search finds "wine" here (underscores split words).
    pr(9, "winetricks: make WINE_BIN overridable"),
]
ISSUES = [
    {"number": 7, "title": "wine: crashes on start"},
    {"number": 8, "title": "Build failure: winetricks"},
]


class Words(unittest.TestCase):
    def test_as_githubs_search_matched_them(self):
        # Checked against GitHub's answers on 2026-10-05.
        self.assertIn("trigger", github_bulk.title_words("nixos: enable led triggers"))
        self.assertIn(
            "velocity", github_bulk.title_words("MidiMonster: above certain velocities")
        )
        self.assertTrue(
            {"wine", "bin"} <= github_bulk.title_words("make WINE_BIN work")
        )
        self.assertEqual(github_bulk.words("_1password-gui"), {"_1password", "gui"})
        self.assertNotIn(
            "_1password", github_bulk.title_words("nixos/1password-gui: x")
        )

    def test_stem(self):
        for word, stemmed in {
            "velocities": "velocity",
            "triggers": "trigger",
            "patches": "patch",
            "class": "class",
            "nixos": "nixo",  # consistently on both sides, so still a match
            "us": "us",
            "status": "status",
        }.items():
            self.assertEqual(github_bulk.stem(word), stemmed, word)


class Listing(unittest.TestCase):
    listing = github_bulk.Listing(PRS, ISSUES)

    def test_whole_words_in_any_case(self):
        # Not winetricks; "Wine 9" and WINE_BIN count, as GitHub's search's do.
        self.assertEqual(self.listing.counts("wine"), (3, 1))
        self.assertEqual(self.listing.counts("winetricks"), (2, 1))

    def test_every_word_of_the_term(self):
        self.assertEqual(self.listing.counts("wesnoth-devel"), (2, 0))
        self.assertEqual(self.listing.counts("python3Packages.requests"), (1, 0))
        self.assertEqual(self.listing.counts("nothing-like-it"), (0, 0))

    def test_open_update_pr(self):
        row = {
            "name": "wesnoth-devel",
            "searchTerm": "wesnoth-devel",
            "nixVersion": "1.19.24",
        }
        # The one aiming highest, as github.open_update_pr picks among a
        # search's results.
        self.assertEqual(self.listing.open_update_pr(row)["number"], 4)
        self.assertIsNone(
            self.listing.open_update_pr(
                {"name": "x", "searchTerm": "x", "nixVersion": "1"}
            )
        )


class ListOpen(unittest.TestCase):
    def page(self, nodes, more, cursor):
        return {"pageInfo": {"hasNextPage": more, "endCursor": cursor}, "nodes": nodes}

    def test_pages_both_until_each_ends(self):
        answers = [
            {
                "repository": {
                    "pullRequests": self.page(PRS[:3], True, "p1"),
                    "issues": self.page(ISSUES, False, "i1"),
                }
            },
            {"repository": {"pullRequests": self.page(PRS[3:], False, "p2")}},
        ]
        with mock.patch.object(github, "graphql", side_effect=answers) as graphql:
            prs, issues = github_bulk.list_open("t")
        self.assertEqual((len(prs), len(issues)), (7, 2))
        second = graphql.call_args_list[1].args[2]
        self.assertEqual(
            (second["prs"], second["morePrs"], second["moreIssues"]),
            ("p1", True, False),
        )

    def test_a_missing_answer_fails_the_listing(self):
        with (
            mock.patch.object(github, "graphql", return_value={}),
            self.assertRaises(ValueError),
        ):
            github_bulk.list_open("t")


class Compare(unittest.TestCase):
    NOW = "2026-10-05T06:00:00+00:00"

    def compare(self, rows):
        out = io.StringIO()
        with (
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github_bulk, "list_open", return_value=(PRS, ISSUES)),
            mock.patch("sys.stderr", out),
        ):
            github_bulk.compare(rows, self.NOW)
        return out.getvalue()

    def test_logs_differences_and_changes_nothing(self):
        rows = [
            {
                "name": "wine",
                "searchTerm": "wine",
                "openPRs": 3,
                "openIssues": 1,
                "countedAt": self.NOW,
                "nixVersion": "10.15",
                "openPR": {"number": 1},
            },
            {
                "name": "winetricks",
                "searchTerm": "winetricks",
                "openPRs": 3,
                "openIssues": 1,
                "countedAt": self.NOW,
                "nixVersion": "20260125",
            },
            {
                "name": "quiet",
                "searchTerm": "quiet",
                "openPRs": 0,
                "openIssues": 0,
                "countedAt": "2026-10-03T06:00:00+00:00",
            },
        ]
        before = [dict(r) for r in rows]
        out = self.compare(rows)
        self.assertEqual(rows, before)
        self.assertIn(
            "7 open PRs and 2 issues; 2 packages counted by search today, "
            "1 agree, 1 differ",
            out,
        )
        self.assertIn(
            "winetricks (winetricks): search 3 PRs, 1 issues, update PR #None; "
            "listing 2, 1, #None",
            out,
        )
        self.assertIn("      winetricks: 20250102 -> 20260125", out)

    def test_failure_only_skips_it(self):
        out = io.StringIO()
        with (
            mock.patch.object(github, "token", return_value="t"),
            mock.patch.object(github_bulk, "list_open", side_effect=OSError("down")),
            mock.patch("sys.stderr", out),
        ):
            github_bulk.compare([], self.NOW)
        self.assertEqual(out.getvalue(), "Bulk PR/issue listing: skipped (down)\n")
