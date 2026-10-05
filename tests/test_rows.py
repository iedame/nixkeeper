import unittest

from nixkeeper.rows import add_source_links, build_rows, search_term, source_url
from tests.helpers import NIXPKGS, nix, other, pkg, project


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

    def test_repo_count_counts_repositories(self):
        # A repository listing the package twice (two subpackages) counts once.
        (row,) = self.rows(
            project(
                "unciv",
                ["unciv"],
                [
                    nix("unciv", "4.22.1", "outdated"),
                    other("debian", "4.22.6", "newest"),
                    other("debian", "4.22.6", "newest"),
                    other("arch", "4.22.6", "newest"),
                ],
                "unciv",
            )
        )
        self.assertEqual(row["repoCount"], 2)

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
        self.assertNotIn("maintainers", row)  # unknown, not none

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

    def test_maintainers_of_all_attributes_once(self):
        nixpkgs = {
            "heroic": pkg("heroic", maintainers=["iedame", "TomaSajt"]),
            "heroic-unwrapped": pkg("heroic", maintainers=["tomasajt", "aidalgol"]),
            "orphan": pkg("orphan"),
        }
        nixpkgs["heroic"]["meta"]["maintainers"].append({"name": "No Handle"})
        entries = [nix("heroic", "1", "newest"), nix("orphan", "1", "newest")]
        heroic, orphan = build_rows(
            {
                "heroic": project(
                    "heroic", ["heroic", "heroic-unwrapped"], entries[:1]
                ),
                "orphan": project("orphan", ["orphan"], entries[1:]),
            },
            nixpkgs,
        )
        self.assertEqual(heroic["maintainers"], ["iedame", "TomaSajt", "aidalgol"])
        self.assertEqual(orphan["maintainers"], [])  # none: searchable as @none

    def test_teams_of_all_attributes_once(self):
        nixpkgs = {
            "steam": pkg("steam"),
            "steam-unwrapped": pkg("steam"),
            "orphan": pkg("orphan"),
        }
        nixpkgs["steam"]["meta"]["teams"] = [{"shortName": "Steam", "scope": "x"}]
        nixpkgs["steam-unwrapped"]["meta"]["teams"] = [
            {"shortName": "Steam"},
            {"shortName": "Gaming"},
            {"scope": "no short name"},
        ]
        entries = [nix("steam", "1", "newest"), nix("orphan", "1", "newest")]
        orphan, steam = build_rows(
            {
                "steam": project("steam", ["steam", "steam-unwrapped"], entries[:1]),
                "orphan": project("orphan", ["orphan"], entries[1:]),
            },
            nixpkgs,
        )
        self.assertEqual(steam["teams"], ["Steam", "Gaming"])
        self.assertNotIn("teams", orphan)  # none: left out

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


class SourceLinks(unittest.TestCase):
    NIXPKGS = {
        "wesnoth": {"meta": {"position": "pkgs/by-name/we/wesnoth/package.nix:147"}},
        "heroic": {"meta": {}},  # no position recorded
        "heroic-unwrapped": {
            "meta": {"position": "pkgs/by-name/he/heroic-unwrapped/package.nix:135"}
        },
    }

    def test_source_url(self):
        self.assertEqual(
            source_url("pkgs/by-name/we/wesnoth/package.nix:147", "abc123"),
            "https://github.com/NixOS/nixpkgs/blob/abc123/pkgs/by-name/we/wesnoth/package.nix#L147",
        )
        self.assertEqual(
            source_url("pkgs/top-level/all-packages.nix", "nixos-unstable"),
            "https://github.com/NixOS/nixpkgs/blob/nixos-unstable/pkgs/top-level/all-packages.nix",
        )

    def test_first_attr_with_a_position(self):
        rows = [
            {"attrs": ["wesnoth"]},
            {"attrs": ["heroic", "heroic-unwrapped"]},
            {"attrs": []},  # not in nixpkgs
            {"attrs": ["gone"]},  # not in the index
        ]
        add_source_links(rows, self.NIXPKGS, "rev")
        self.assertTrue(
            rows[0]["source"].endswith("/rev/pkgs/by-name/we/wesnoth/package.nix#L147")
        )
        self.assertTrue(
            rows[1]["source"].endswith(
                "/rev/pkgs/by-name/he/heroic-unwrapped/package.nix#L135"
            )
        )
        self.assertNotIn("source", rows[2])
        self.assertNotIn("source", rows[3])


class NewestVersion(unittest.TestCase):
    """refVersion: the newest version elsewhere."""

    def ref(self, entries):
        (row,) = build_rows(
            {"p": project("p", ["p"], [nix("p", "1.0", "outdated"), *entries], "p")}, {}
        )
        return row["refVersion"]

    def test_only_nix_packages_it(self):
        """msedgedriver: a stable branch got the update first (a backport);
        Repology marks it unique, not newest, as no other family has it."""
        entries = [
            other("nix_stable_26_05", "1.2", "unique"),
            other("nix_stable_25_11", "0.9", "outdated"),
        ]
        self.assertEqual(self.ref(entries), "1.2")

    def test_unique_only_when_none_is_newest(self):
        entries = [other("debian", "1.1", "newest"), other("odd", "9.9", "unique")]
        self.assertEqual(self.ref(entries), "1.1")

    def test_the_highest_not_the_first(self):
        entries = [other("a", "1.9", "newest"), other("b", "1.10", "newest")]
        self.assertEqual(self.ref(entries), "1.10")

    def test_none_known(self):
        self.assertIsNone(self.ref([other("a", "0.9", "outdated")]))
