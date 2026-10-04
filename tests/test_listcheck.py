"""Mistakes in the package lists, found at every sync (nixkeeper/listcheck.py)."""

import unittest

from nixkeeper import listcheck

from .helpers import pkg

NIXPKGS = {
    "unciv": pkg("unciv", maintainers=["iedame"]),
    "wesnoth": pkg("wesnoth", maintainers=["someone"]),
    "python313Packages.requests": pkg("requests"),
}


def lists(**fields):
    return {"maintainers": ["iedame"], "extraPackages": {}, **fields}


class Problems(unittest.TestCase):
    def check(self, found_lists, tracked=("unciv",)):
        return listcheck.problems(found_lists, NIXPKGS, list(tracked))

    def test_good_lists(self):
        self.assertEqual(self.check(lists()), [])

    def test_a_handle_no_package_lists(self):
        found = self.check(lists(maintainers=["iedame", "iedme"]))
        self.assertEqual(len(found), 1)
        self.assertIn("lists iedme as a maintainer (a typo?)", found[0])

    def test_handles_ignore_case(self):
        self.assertEqual(self.check(lists(maintainers=["IEDAME"])), [])

    def test_an_extra_package_nixpkgs_doesnt_have(self):
        found = self.check(
            lists(extraPackages={"games": ["wesnoth", "python3Packages.requests"]})
        )
        self.assertEqual(len(found), 1)
        self.assertIn("extraPackages.games: python3Packages.requests", found[0])

    def test_checks_and_rules_for_untracked_packages(self):
        found = self.check(
            lists(
                updateChecks={"unciv": {}, "stepmania": {}},
                ignoredUpdates={"xskat": {"4.0-9": "never released"}},
                upToDate={"pacvim": {"version": "2018-05-16", "reason": "x"}},
            )
        )
        self.assertEqual(
            found,
            [
                "updateChecks: stepmania isn't a tracked package",
                "ignoredUpdates: xskat isn't a tracked package",
                "upToDate: pacvim isn't a tracked package",
            ],
        )

    def test_an_unknown_page_theme(self):
        self.assertEqual(self.check(lists(page={"theme": "catppuccin"})), [])
        self.assertEqual(
            self.check(lists(page={"theme": "mocha"})),
            ["page.theme: mocha isn't one of the page's themes (classic, catppuccin)"],
        )

    def test_a_plain_extra_list(self):
        found = self.check(lists(extraPackages=["nosuchpkg"]))
        self.assertIn("extraPackages.extra: nosuchpkg", found[0])


class PageSettings(unittest.TestCase):
    def test_the_theme_when_known(self):
        self.assertEqual(
            listcheck.page_settings(lists(page={"theme": "catppuccin"})),
            {"theme": "catppuccin"},
        )

    def test_nothing_otherwise(self):
        self.assertEqual(listcheck.page_settings(lists()), {})
        self.assertEqual(listcheck.page_settings(lists(page={"theme": "mocha"})), {})


if __name__ == "__main__":
    unittest.main()
