import io
import unittest
from unittest import mock

from nixkeeper.tracking import tracked_packages
from tests.helpers import NIXPKGS


class TrackedPackages(unittest.TestCase):
    def wanted(self, extra=(), maintainers=("iedame",)):
        with mock.patch("sys.stderr", io.StringIO()):
            return tracked_packages(
                {"maintainers": list(maintainers), "extraPackages": list(extra)},
                NIXPKGS,
            )

    def test_maintained_packages_one_attr_each_any_case(self):
        w = self.wanted()
        self.assertEqual(w["wesnoth"], (["wesnoth"], "wesnoth"))
        self.assertEqual(
            w["wesnoth-devel"], (["wesnoth-devel"], "wesnoth-devel")
        )  # "IEDAME"
        self.assertEqual(
            w["heroic-unwrapped"], (["heroic-unwrapped"], "heroic-unwrapped")
        )

    def test_maintained_nested_package_uses_pname_as_fallback(self):
        self.assertEqual(
            self.wanted()["python313Packages.requests"],
            (["python313Packages.requests"], "requests"),
        )

    def test_exact_attribute_tracks_only_that_package(self):
        w = self.wanted(["_1password-gui", "haskellPackages.pandoc"], maintainers=[])
        self.assertEqual(w["_1password-gui"], (["_1password-gui"], "_1password-gui"))
        self.assertEqual(
            w["haskellPackages.pandoc"],
            (["haskellPackages.pandoc"], "haskellPackages.pandoc"),
        )

    def test_pname_matches_every_top_level_package_with_it(self):
        w = self.wanted(["1password"], maintainers=[])
        self.assertEqual(
            w["1password"], (["_1password-gui", "_1password-gui-beta"], "1password")
        )

    def test_pname_ignores_nested_sets(self):
        # haskellPackages.pandoc shares the pname "pandoc".
        self.assertEqual(
            self.wanted(["pandoc"], maintainers=[])["pandoc"], (["pandoc"], "pandoc")
        )

    def test_unknown_entry_has_no_attrs(self):
        self.assertEqual(
            self.wanted(["python3Packages.requests"], maintainers=[])[
                "python3Packages.requests"
            ],
            ([], "python3Packages.requests"),
        )

    def test_maintained_entry_wins_over_same_name_in_lists(self):
        self.assertEqual(self.wanted(["wesnoth"])["wesnoth"], (["wesnoth"], "wesnoth"))
