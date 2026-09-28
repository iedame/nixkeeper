import unittest

from nixkeeper.rows import build_rows, search_term
from tests.helpers import NIXPKGS, nix, other, project


class Rows(unittest.TestCase):
    def rows(self, *projects):
        return build_rows({p["project"] or p["name"]: p for p in projects}, NIXPKGS)

    WESNOTH = [
        nix("wesnoth", "1.18.8", "newest"),
        nix("wesnoth-devel", "1.19.24", "devel"),
        other("debian", "1.18.8", "newest"),
        other("arch", "1.19.24", "devel"),
    ]

    def test_different_versions_split_into_rows(self):
        stable, devel = self.rows(
            project("wesnoth", ["wesnoth", "wesnoth-devel"], self.WESNOTH, "wesnoth")
        )
        self.assertEqual(
            (stable["name"], stable["nixVersion"], stable["devel"]),
            ("wesnoth", "1.18.8", False),
        )
        self.assertEqual(
            (devel["name"], devel["nixVersion"], devel["devel"]),
            ("wesnoth-devel", "1.19.24", True),
        )

    def test_devel_row_compares_against_devel_versions(self):
        stable, devel = self.rows(
            project("wesnoth", ["wesnoth", "wesnoth-devel"], self.WESNOTH, "wesnoth")
        )
        self.assertEqual(stable["refVersion"], "1.18.8")
        self.assertEqual(devel["refVersion"], "1.19.24")

    def test_untracked_variant_is_ignored(self):
        [row] = self.rows(project("wesnoth", ["wesnoth"], self.WESNOTH, "wesnoth"))
        self.assertEqual(
            (row["name"], row["nixVersion"], row["devel"]), ("wesnoth", "1.18.8", False)
        )

    def test_same_version_variants_stay_one_row(self):
        entries = [
            nix("heroic", "2.22.3", "newest"),
            nix("heroic-unwrapped", "2.22.3", "newest"),
        ]
        [row] = self.rows(
            project(
                "heroic-unwrapped",
                ["heroic-unwrapped", "heroic"],
                entries,
                "heroic-games-launcher",
            )
        )
        self.assertEqual(row["name"], "heroic")  # first attr alphabetically
        self.assertEqual(row["attrs"], ["heroic", "heroic-unwrapped"])
        self.assertEqual(row["project"], "heroic-games-launcher")

    def test_variants_sharing_a_pname_are_named_by_attribute(self):
        entries = [
            nix("_1password-gui", "8.12.36", "newest"),
            nix("_1password-gui-beta", "8.12.32-26.BETA", "legacy"),
            other("aur", "8.12.36", "newest"),
            other("aur", "8.12.38_25.BETA", "ignored"),
        ]
        stable, beta = self.rows(
            project(
                "_1password-gui",
                ["_1password-gui", "_1password-gui-beta"],
                entries,
                "1password",
            )
        )
        self.assertEqual(
            (stable["name"], stable["searchTerm"]), ("_1password-gui", "_1password-gui")
        )
        self.assertEqual(
            (beta["name"], beta["searchTerm"]),
            ("_1password-gui-beta", "_1password-gui-beta"),
        )
        self.assertEqual((beta["nixStatus"], beta["devel"]), ("legacy", True))
        # No devel version elsewhere (the aur beta is "ignored"): falls back to stable.
        self.assertEqual(beta["refVersion"], "8.12.36")

    def test_repology_devel_status_marks_single_row_devel(self):
        [row] = self.rows(
            project(
                "lincity", ["lincity"], [nix("lincity", "1.13.1", "devel")], "lincity"
            )
        )
        self.assertTrue(row["devel"])

    def test_nested_package_uses_its_own_nix_entry(self):
        entries = [
            nix("pandoc", "3.8", "newest"),
            nix("haskellPackages.pandoc", "3.7.0.2", "legacy"),
        ]
        [row] = self.rows(
            project(
                "haskellPackages.pandoc", ["haskellPackages.pandoc"], entries, "pandoc"
            )
        )
        self.assertEqual(
            (row["name"], row["nixVersion"], row["nixStatus"]),
            ("haskellPackages.pandoc", "3.7.0.2", "legacy"),
        )

    def test_not_in_nixpkgs(self):
        [row] = self.rows(project("python3Packages.requests", [], []))
        self.assertEqual(row["name"], "python3Packages.requests")
        self.assertEqual(
            (row["nixStatus"], row["nixVersion"], row["project"]),
            ("missing", None, None),
        )
        self.assertNotIn("platforms", row)  # not "any platform"
        self.assertNotIn("homepage", row)

    def test_platforms(self):
        def plat(attr):
            [row] = self.rows(project(attr, [attr], [nix(attr, "1", "newest")], attr))
            return row["platforms"]

        self.assertEqual(plat("wesnoth"), {"linux": True, "darwin": True})
        self.assertEqual(plat("heroic"), {"linux": True, "darwin": False})
        self.assertEqual(plat("bbedit"), {"linux": False, "darwin": True})
        self.assertIsNone(plat("fzssh"))  # nothing declared: unrestricted
        self.assertEqual(
            plat("odd"), {"linux": True, "darwin": False}
        )  # pattern entries ignored

    def test_homepage_takes_first_of_a_list(self):
        [row] = self.rows(
            project(
                "heroic",
                ["heroic"],
                [nix("heroic", "1", "newest")],
                "heroic-games-launcher",
            )
        )
        self.assertEqual(row["homepage"], "https://heroic.example")

    def test_versioned_python_sets_search_by_alias(self):
        entries = [nix("python313Packages.requests", "2.34.2", "newest")]
        [row] = self.rows(
            project(
                "python313Packages.requests",
                ["python313Packages.requests"],
                entries,
                "python:requests",
            )
        )
        self.assertEqual(row["name"], "python313Packages.requests")
        self.assertEqual(row["searchTerm"], "python3Packages.requests")
        self.assertEqual(row["dataFile"], "python_requests.json")

    def test_stale_marker_carried_to_every_row_of_the_project(self):
        rows = self.rows(
            project(
                "wesnoth",
                ["wesnoth", "wesnoth-devel"],
                self.WESNOTH,
                "wesnoth",
                staleSince="2026-09-01",
            )
        )
        self.assertEqual([r["staleSince"] for r in rows], ["2026-09-01", "2026-09-01"])

    def test_rows_sorted_by_name_ignoring_case(self):
        rows = self.rows(
            project("bbedit", ["bbedit"], [], "bbedit"),
            project("_1password-gui", ["_1password-gui"], [], "1password"),
            project("Zed", [], []),
        )
        self.assertEqual([r["name"] for r in rows], ["_1password-gui", "bbedit", "Zed"])


class SearchTerm(unittest.TestCase):
    def test_search_term(self):
        self.assertEqual(
            search_term("python314Packages.numpy"), "python3Packages.numpy"
        )
        self.assertEqual(
            search_term("haskellPackages.pandoc"), "haskellPackages.pandoc"
        )
        self.assertEqual(search_term("heroic"), "heroic")
