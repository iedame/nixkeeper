import unittest

from nixkeeper.rows import (
    add_source_links,
    build_rows,
    channel_versions,
    search_term,
    source_url,
)
from nixkeeper.sources import nixpkgs as nixpkgs_source
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

    def test_an_older_series_split_off_isnt_devel(self):
        entries = [
            nix("gnumake", "4.4.1", "newest"),
            nix("gnumake42", "4.2.1", "legacy"),
            other("arch", "4.4.1", "newest"),
        ]
        stable, older = self.rows(
            project("gnumake", ["gnumake", "gnumake42"], entries, "gnumake")
        )
        self.assertEqual((stable["name"], stable["devel"]), ("gnumake", False))
        self.assertEqual((older["name"], older["devel"]), ("gnumake42", False))
        self.assertEqual(older["keptBeside"], {"attr": "gnumake", "version": "4.4.1"})

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
        # Kept beside the newer one, which the page names.
        self.assertEqual(row["keptBeside"], {"attr": "pandoc", "version": "3.8"})

    def test_kept_beside_the_plainest_name_of_the_newest(self):
        entries = [
            nix("tracy", "0.14.1", "newest"),
            nix("tracy_0_14", "0.14.1", "newest"),
            nix("tracy_0_13", "0.13.1", "legacy"),
            nix("tracy_0_11", "0.11.1", "legacy"),
        ]
        [row] = self.rows(project("tracy_0_11", ["tracy_0_11"], entries, "tracy"))
        self.assertEqual(row["keptBeside"], {"attr": "tracy", "version": "0.14.1"})
        [newest] = self.rows(project("tracy", ["tracy"], entries, "tracy"))
        self.assertNotIn("keptBeside", newest)

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

    def test_in_nixpkgs_but_repology_lists_other_repositories_only(self):
        # keeperrl: Repology has a project of that name (other repositories'
        # packages), but not nixpkgs' (its version "alpha34" it can't read).
        nixpkgs = {
            "keeperrl": {**pkg("keeperrl", ["x86_64-linux"]), "version": "alpha34"}
        }
        [row] = build_rows(
            {
                "keeperrl": project(
                    "keeperrl",
                    ["keeperrl"],
                    [other("openbsd", "1.3", "newest")],
                    "keeperrl",
                )
            },
            nixpkgs,
        )
        self.assertEqual((row["nixStatus"], row["nixVersion"]), ("unlisted", "alpha34"))

    def test_platforms(self):
        def plat(attr):
            [row] = self.rows(project(attr, [attr], [nix(attr, "1", "newest")], attr))
            return row["platforms"]

        self.assertEqual(plat("wesnoth"), {"linux": True, "darwin": True})
        self.assertEqual(plat("heroic"), {"linux": True, "darwin": False})
        self.assertEqual(plat("bbedit"), {"linux": False, "darwin": True})
        self.assertIsNone(plat("fzssh"))  # nothing declared: unrestricted
        self.assertEqual(
            plat("odd"),  # pattern entries ignored
            {"linux": True, "darwin": False, "systems": ["x86_64-linux"]},
        )

    def test_platforms_by_system(self):
        def plat(platforms, bad=None):
            meta = {"platforms": platforms}
            if bad:
                meta["badPlatforms"] = bad
            return nixpkgs_source.platforms([{"meta": meta}])

        every = ["x86_64-linux", "aarch64-linux", "aarch64-darwin"]
        self.assertEqual(plat(every), {"linux": True, "darwin": True})
        # A Linux system missing: which ones, then.
        self.assertEqual(
            plat(["x86_64-linux", "aarch64-darwin"]),
            {
                "linux": True,
                "darwin": True,
                "systems": ["aarch64-darwin", "x86_64-linux"],
            },
        )
        self.assertEqual(
            plat(["aarch64-linux"]),
            {"linux": True, "darwin": False, "systems": ["aarch64-linux"]},
        )
        # meta.badPlatforms takes systems away.
        self.assertEqual(
            plat(every, bad=["aarch64-linux"]),
            {
                "linux": True,
                "darwin": True,
                "systems": ["aarch64-darwin", "x86_64-linux"],
            },
        )
        self.assertEqual(
            plat(every, bad=["aarch64-darwin"]), {"linux": True, "darwin": False}
        )
        # Only x86_64-darwin, which nixpkgs no longer builds: Darwin, but none
        # of the systems it builds.
        self.assertEqual(
            plat(["x86_64-darwin"]), {"linux": False, "darwin": True, "systems": []}
        )

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

    def test_named_after_a_top_level_attribute(self):
        entries = [
            nix("azure-sdk-for-cpp.cmake", "4", "newest"),
            nix("cmake", "4", "newest"),
        ]
        nixpkgs = {"cmake": pkg("cmake"), "azure-sdk-for-cpp.cmake": pkg("cmake")}
        (row,) = build_rows(
            {"cmake": project("cmake", ["azure-sdk-for-cpp.cmake", "cmake"], entries)},
            nixpkgs,
        )
        self.assertEqual((row["name"], row["searchTerm"]), ("cmake", "cmake"))

    def test_marked_broken_from_the_index(self):
        nixpkgs = {"a": pkg("a"), "b": pkg("b")}
        nixpkgs["a"]["meta"]["broken"] = True
        entries = [nix("a", "1", "newest"), nix("b", "1", "newest")]
        a, b = build_rows(
            {
                "a": project("a", ["a"], entries[:1]),
                "b": project("b", ["b"], entries[1:]),
            },
            nixpkgs,
        )
        self.assertTrue(a["markedBroken"])
        self.assertNotIn("markedBroken", b)

    def test_direct_maintainers_beside_teams(self):
        def person(handle):
            return {"github": handle, "githubId": 1}

        nixpkgs = {"gdal": pkg("gdal"), "plain": pkg("plain"), "old": pkg("old")}
        geo = {"shortName": "Geospatial"}
        nixpkgs["gdal"]["meta"].update(
            teams=[geo],
            maintainers=[person("tviti"), person("l0b0"), person("sikmir")],
            nonTeamMaintainers=[person("tviti")],
        )
        nixpkgs["plain"]["meta"].update(
            teams=[geo],
            maintainers=[person("l0b0")],
            nonTeamMaintainers=[person("l0b0")],  # the same: not repeated
        )
        nixpkgs["old"]["meta"].update(teams=[geo], maintainers=[person("x")])
        entries = [nix(n, "1", "newest") for n in ("gdal", "old", "plain")]
        gdal, old, plain = build_rows(
            {e["srcname"]: project(e["srcname"], [e["srcname"]], [e]) for e in entries},
            nixpkgs,
        )
        self.assertEqual(gdal["nonTeamMaintainers"], ["tviti"])
        self.assertNotIn("nonTeamMaintainers", plain)
        self.assertNotIn("nonTeamMaintainers", old)  # the index doesn't say

    def test_marked_insecure_from_the_index(self):
        nixpkgs = {"a": pkg("a"), "a-bin": pkg("a"), "b": pkg("b")}
        nixpkgs["a"]["meta"]["knownVulnerabilities"] = ["CVE-2020-25031"]
        nixpkgs["a-bin"]["meta"]["knownVulnerabilities"] = [
            "CVE-2020-25031",  # once
            "Uses Electron 37, EOL",
        ]
        entries = [nix("a", "1", "newest"), nix("b", "1", "newest")]
        a, b = build_rows(
            {
                "a": project("a", ["a", "a-bin"], entries[:1]),
                "b": project("b", ["b"], entries[1:]),
            },
            nixpkgs,
        )
        self.assertEqual(
            a["markedInsecure"], ["CVE-2020-25031", "Uses Electron 37, EOL"]
        )
        self.assertNotIn("markedInsecure", b)

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


class ChannelVersions(unittest.TestCase):
    """nixVersion from the channel's index, when Repology hasn't caught up."""

    def row(self, status, channel, ref="2.0", attrs=("p",), index=None):
        entries = [nix("p", "1.0", status)]
        if ref:
            entries.append(other("debian", ref, "newest"))
        (row,) = build_rows({"p": project("p", list(attrs), entries, "p")}, {})
        index = index or {a: pkg(a, version=channel) for a in attrs}
        changed = channel_versions([row], index)
        return row, changed

    def test_caught_up(self):
        """microsoft-edge, 2026-10-08: the channel had .62, Repology .53."""
        row, changed = self.row("outdated", "2.0")
        self.assertEqual(changed, ["p"])
        self.assertEqual(
            (row["nixVersion"], row["nixStatus"], row["repologyVersion"]),
            ("2.0", "newest", "1.0"),
        )

    def test_still_behind(self):
        row, _ = self.row("outdated", "1.5")
        self.assertEqual((row["nixVersion"], row["nixStatus"]), ("1.5", "outdated"))

    def test_newest_stays_newest(self):
        row, _ = self.row("newest", "1.1", ref=None)
        self.assertEqual((row["nixVersion"], row["nixStatus"]), ("1.1", "newest"))

    def test_outdated_against_nothing_named(self):
        row, _ = self.row("outdated", "1.1", ref=None)
        self.assertEqual((row["nixVersion"], row["nixStatus"]), ("1.1", "outdated"))

    def test_not_older(self):
        row, changed = self.row("outdated", "0.9")
        self.assertEqual((changed, row["nixVersion"]), ([], "1.0"))
        self.assertNotIn("repologyVersion", row)

    def test_letters_only_are_repology_rules(self):
        """thunderbird-esr-bin: 153.3.1esr, which Repology has as 153.3.1."""
        row, changed = self.row("outdated", "1.0esr")
        self.assertEqual((changed, row["nixVersion"]), ([], "1.0"))

    def test_attributes_disagreeing(self):
        index = {"p": pkg("p", version="2.0"), "q": pkg("q", version="1.0")}
        _, changed = self.row("outdated", None, attrs=("p", "q"), index=index)
        self.assertEqual(changed, [])

    def test_statuses_left_alone(self):
        """A kept older version, or one Repology distrusts."""
        for status in ("legacy", "untrusted", "noscheme", "ignored"):
            with self.subTest(status):
                _, changed = self.row(status, "2.0")
                self.assertEqual(changed, [])
