"""Tests for fetch.py's decision-making. No network: Repology, GitHub and the
nixpkgs index are replaced by small hand-written samples.

Run with `nix flake check`, or `python3 -m unittest -v test_fetch` from
scripts/ inside `nix develop`.
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import fetch


def pkg(pname, platforms=None, maintainers=(), homepage=None):
    """A nixpkgs index entry, trimmed to the fields fetch.py reads."""
    meta = {"maintainers": [{"github": m} for m in maintainers]}
    if platforms is not None:
        meta["platforms"] = platforms
    if homepage is not None:
        meta["homepage"] = homepage
    return {"pname": pname, "meta": meta}


def nix(srcname, version, status):
    return {"repo": "nix_unstable", "srcname": srcname, "version": version, "status": status}


def other(repo, version, status):
    return {"repo": repo, "srcname": "x", "version": version, "status": status}


def project(name, attrs, entries, project_name=None, **extra):
    """A collect_projects() result entry."""
    key = project_name or name
    return {"name": name, "project": project_name, "attrs": attrs, "entries": entries,
            "dataFile": fetch.data_file(key), **extra}


LINUX = ["x86_64-linux", "aarch64-linux"]
DARWIN = ["aarch64-darwin"]

NIXPKGS = {
    "wesnoth": pkg("wesnoth", LINUX + DARWIN, ["iedame"], "https://www.wesnoth.org/"),
    "wesnoth-devel": pkg("wesnoth-devel", LINUX + DARWIN, ["IEDAME"]),
    "heroic": pkg("heroic", LINUX, ["iedame"], ["https://heroic.example", "https://mirror.example"]),
    "heroic-unwrapped": pkg("heroic-unwrapped", LINUX, ["iedame"]),
    "typstPackages.heroic": pkg("heroic", LINUX),
    "_1password-gui": pkg("1password", LINUX + DARWIN),
    "_1password-gui-beta": pkg("1password", LINUX + DARWIN),
    "bbedit": pkg("bbedit", DARWIN),
    "fzssh": pkg("fzssh"),  # no platforms declared
    "lincity": pkg("lincity"),
    "pandoc": pkg("pandoc", LINUX + DARWIN),
    "haskellPackages.pandoc": pkg("pandoc", LINUX + DARWIN),
    "python313Packages.requests": pkg("requests", LINUX + DARWIN, ["iedame"]),
    "odd": pkg("odd", ["x86_64-linux", {"kernel": {"name": "darwin"}}]),
}


class TrackedPackages(unittest.TestCase):
    def wanted(self, extra=(), maintainers=("iedame",)):
        with mock.patch("sys.stderr", io.StringIO()):
            return fetch.tracked_packages(
                {"maintainers": list(maintainers), "extraPackages": list(extra)}, NIXPKGS)

    def test_maintained_packages_one_attr_each_any_case(self):
        w = self.wanted()
        self.assertEqual(w["wesnoth"], (["wesnoth"], "wesnoth"))
        self.assertEqual(w["wesnoth-devel"], (["wesnoth-devel"], "wesnoth-devel"))  # "IEDAME"
        self.assertEqual(w["heroic-unwrapped"], (["heroic-unwrapped"], "heroic-unwrapped"))

    def test_maintained_nested_package_uses_pname_as_fallback(self):
        self.assertEqual(self.wanted()["python313Packages.requests"],
                         (["python313Packages.requests"], "requests"))

    def test_exact_attribute_tracks_only_that_package(self):
        w = self.wanted(["_1password-gui", "haskellPackages.pandoc"], maintainers=[])
        self.assertEqual(w["_1password-gui"], (["_1password-gui"], "_1password-gui"))
        self.assertEqual(w["haskellPackages.pandoc"], (["haskellPackages.pandoc"], "haskellPackages.pandoc"))

    def test_pname_matches_every_top_level_package_with_it(self):
        w = self.wanted(["1password"], maintainers=[])
        self.assertEqual(w["1password"], (["_1password-gui", "_1password-gui-beta"], "1password"))

    def test_pname_ignores_nested_sets(self):
        # "heroic" is both an attribute and a pname; "pandoc" is too, and
        # haskellPackages.pandoc shares the pname.
        w = self.wanted(["pandoc"], maintainers=[])
        self.assertEqual(w["pandoc"], (["pandoc"], "pandoc"))

    def test_unknown_entry_has_no_attrs(self):
        self.assertEqual(self.wanted(["python3Packages.requests"], maintainers=[])["python3Packages.requests"],
                         ([], "python3Packages.requests"))

    def test_maintained_entry_wins_over_same_name_in_lists(self):
        self.assertEqual(self.wanted(["wesnoth"])["wesnoth"], (["wesnoth"], "wesnoth"))


class Rows(unittest.TestCase):
    def rows(self, *projects):
        return fetch.build_rows({p["project"] or p["name"]: p for p in projects}, NIXPKGS)

    WESNOTH = [
        nix("wesnoth", "1.18.8", "newest"), nix("wesnoth-devel", "1.19.24", "devel"),
        other("debian", "1.18.8", "newest"), other("arch", "1.19.24", "devel"),
    ]

    def test_different_versions_split_into_rows(self):
        stable, devel = self.rows(project("wesnoth", ["wesnoth", "wesnoth-devel"], self.WESNOTH, "wesnoth"))
        self.assertEqual((stable["name"], stable["nixVersion"], stable["devel"]), ("wesnoth", "1.18.8", False))
        self.assertEqual((devel["name"], devel["nixVersion"], devel["devel"]), ("wesnoth-devel", "1.19.24", True))

    def test_devel_row_compares_against_devel_versions(self):
        stable, devel = self.rows(project("wesnoth", ["wesnoth", "wesnoth-devel"], self.WESNOTH, "wesnoth"))
        self.assertEqual(stable["refVersion"], "1.18.8")
        self.assertEqual(devel["refVersion"], "1.19.24")

    def test_untracked_variant_is_ignored(self):
        [row] = self.rows(project("wesnoth", ["wesnoth"], self.WESNOTH, "wesnoth"))
        self.assertEqual((row["name"], row["nixVersion"], row["devel"]), ("wesnoth", "1.18.8", False))

    def test_same_version_variants_stay_one_row(self):
        entries = [nix("heroic", "2.22.3", "newest"), nix("heroic-unwrapped", "2.22.3", "newest")]
        [row] = self.rows(project("heroic-unwrapped", ["heroic-unwrapped", "heroic"], entries, "heroic-games-launcher"))
        self.assertEqual(row["name"], "heroic")  # first attr alphabetically
        self.assertEqual(row["attrs"], ["heroic", "heroic-unwrapped"])
        self.assertEqual(row["project"], "heroic-games-launcher")

    def test_variants_sharing_a_pname_are_named_by_attribute(self):
        entries = [nix("_1password-gui", "8.12.36", "newest"), nix("_1password-gui-beta", "8.12.32-26.BETA", "legacy"),
                   other("aur", "8.12.36", "newest"), other("aur", "8.12.38_25.BETA", "ignored")]
        stable, beta = self.rows(project("_1password-gui", ["_1password-gui", "_1password-gui-beta"], entries, "1password"))
        self.assertEqual((stable["name"], stable["searchTerm"]), ("_1password-gui", "_1password-gui"))
        self.assertEqual((beta["name"], beta["searchTerm"]), ("_1password-gui-beta", "_1password-gui-beta"))
        self.assertEqual((beta["nixStatus"], beta["devel"]), ("legacy", True))
        # No devel version elsewhere (the aur beta is "ignored"): falls back to stable.
        self.assertEqual(beta["refVersion"], "8.12.36")

    def test_repology_devel_status_marks_single_row_devel(self):
        [row] = self.rows(project("lincity", ["lincity"], [nix("lincity", "1.13.1", "devel")], "lincity"))
        self.assertTrue(row["devel"])

    def test_nested_package_uses_its_own_nix_entry(self):
        entries = [nix("pandoc", "3.8", "newest"), nix("haskellPackages.pandoc", "3.7.0.2", "legacy")]
        [row] = self.rows(project("haskellPackages.pandoc", ["haskellPackages.pandoc"], entries, "pandoc"))
        self.assertEqual((row["name"], row["nixVersion"], row["nixStatus"]), ("haskellPackages.pandoc", "3.7.0.2", "legacy"))

    def test_not_in_nixpkgs(self):
        [row] = self.rows(project("python3Packages.requests", [], []))
        self.assertEqual(row["name"], "python3Packages.requests")
        self.assertEqual((row["nixStatus"], row["nixVersion"], row["project"]), ("missing", None, None))
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
        self.assertEqual(plat("odd"), {"linux": True, "darwin": False})  # pattern entries ignored

    def test_homepage_takes_first_of_a_list(self):
        [row] = self.rows(project("heroic", ["heroic"], [nix("heroic", "1", "newest")], "heroic-games-launcher"))
        self.assertEqual(row["homepage"], "https://heroic.example")

    def test_versioned_python_sets_search_by_alias(self):
        entries = [nix("python313Packages.requests", "2.34.2", "newest")]
        [row] = self.rows(project("python313Packages.requests", ["python313Packages.requests"], entries, "python:requests"))
        self.assertEqual(row["name"], "python313Packages.requests")
        self.assertEqual(row["searchTerm"], "python3Packages.requests")
        self.assertEqual(row["dataFile"], "python_requests.json")

    def test_stale_marker_carried_to_every_row_of_the_project(self):
        rows = self.rows(project("wesnoth", ["wesnoth", "wesnoth-devel"], self.WESNOTH, "wesnoth", staleSince="2026-09-01"))
        self.assertEqual([r["staleSince"] for r in rows], ["2026-09-01", "2026-09-01"])

    def test_rows_sorted_by_name_ignoring_case(self):
        rows = self.rows(project("bbedit", ["bbedit"], [], "bbedit"),
                         project("_1password-gui", ["_1password-gui"], [], "1password"),
                         project("Zed", [], []))
        self.assertEqual([r["name"] for r in rows], ["_1password-gui", "bbedit", "Zed"])


class Naming(unittest.TestCase):
    def test_data_file_is_safe(self):
        self.assertEqual(fetch.data_file("python:requests"), "python_requests.json")
        self.assertEqual(fetch.data_file("wesnoth"), "wesnoth.json")
        self.assertEqual(fetch.data_file("a/b c"), "a_b_c.json")

    def test_search_term(self):
        self.assertEqual(fetch.search_term("python314Packages.numpy"), "python3Packages.numpy")
        self.assertEqual(fetch.search_term("haskellPackages.pandoc"), "haskellPackages.pandoc")
        self.assertEqual(fetch.search_term("heroic"), "heroic")


class CollectProjects(unittest.TestCase):
    def setUp(self):
        self.stderr = mock.patch("sys.stderr", io.StringIO())
        self.stderr.start()
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.stderr.stop()
        self.dir.cleanup()

    def write_previous(self, packages, checked_at="2026-09-20T06:00:00+00:00", files=None):
        with open(os.path.join(self.dir.name, "index.json"), "w") as f:
            json.dump({"checkedAt": checked_at, "packages": packages}, f)
        for name, entries in (files or {}).items():
            with open(os.path.join(self.dir.name, name), "w") as f:
                json.dump(entries, f)
        return fetch.load_previous_run(self.dir.name)

    def collect(self, wanted, previous, answers):
        """answers: fallback name -> (project, entries), or an exception."""
        def resolve(fallback, attrs):
            answer = answers[fallback]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return fetch.collect_projects(wanted, previous, resolve, self.dir.name)

    def test_attrs_resolving_to_one_project_merge(self):
        entries = [nix("wesnoth", "1.18.8", "newest")]
        projects = self.collect(
            {"wesnoth": (["wesnoth"], "wesnoth"), "wesnoth-devel": (["wesnoth-devel"], "wesnoth-devel")},
            {"packages": []},
            {"wesnoth": ("wesnoth", entries), "wesnoth-devel": ("wesnoth", entries)})
        self.assertEqual(list(projects), ["wesnoth"])
        self.assertEqual(projects["wesnoth"]["attrs"], ["wesnoth", "wesnoth-devel"])

    def test_unknown_to_repology_keyed_by_name(self):
        projects = self.collect({"nope": ([], "nope")}, {"packages": []}, {"nope": (None, None)})
        self.assertEqual(projects["nope"]["project"], None)
        self.assertEqual(projects["nope"]["entries"], [])

    def test_failed_lookup_reuses_previous_data(self):
        entries = [nix("wesnoth", "1.18.8", "newest")]
        previous = self.write_previous(
            [{"name": "wesnoth", "searchTerm": "wesnoth", "attrs": ["wesnoth"], "project": "wesnoth", "dataFile": "wesnoth.json"}],
            files={"wesnoth.json": entries})
        projects = self.collect(
            {"wesnoth": (["wesnoth"], "wesnoth"), "bbedit": (["bbedit"], "bbedit"), "fzssh": (["fzssh"], "fzssh")},
            previous,
            {"wesnoth": urllib.error.URLError("down"), "bbedit": ("bbedit", []), "fzssh": ("fzssh", [])})
        self.assertEqual(projects["wesnoth"]["entries"], entries)
        self.assertEqual(projects["wesnoth"]["staleSince"], "2026-09-20T06:00:00+00:00")
        self.assertNotIn("staleSince", projects["bbedit"])

    def test_repeated_failure_keeps_original_date(self):
        previous = self.write_previous(
            [{"name": "wesnoth", "attrs": ["wesnoth"], "project": "wesnoth", "dataFile": "wesnoth.json",
              "staleSince": "2026-09-01T06:00:00+00:00"}],
            files={"wesnoth.json": []})
        projects = self.collect(
            {"wesnoth": (["wesnoth"], "wesnoth"), "bbedit": (["bbedit"], "bbedit"), "fzssh": (["fzssh"], "fzssh")},
            previous,
            {"wesnoth": OSError("down"), "bbedit": ("bbedit", []), "fzssh": ("fzssh", [])})
        self.assertEqual(projects["wesnoth"]["staleSince"], "2026-09-01T06:00:00+00:00")

    def test_failed_lookup_without_previous_data_is_skipped(self):
        projects = self.collect(
            {"new": (["new"], "new"), "bbedit": (["bbedit"], "bbedit"), "fzssh": (["fzssh"], "fzssh")},
            {"packages": []},
            {"new": OSError("down"), "bbedit": ("bbedit", []), "fzssh": ("fzssh", [])})
        self.assertEqual(sorted(projects), ["bbedit", "fzssh"])

    def test_more_than_half_failing_aborts(self):
        wanted = {n: ([n], n) for n in "abc"}
        with self.assertRaises(SystemExit):
            self.collect(wanted, {"packages": []}, {"a": OSError(), "b": OSError(), "c": ("c", [])})

    def test_exactly_half_failing_continues(self):
        wanted = {n: ([n], n) for n in "abcd"}
        projects = self.collect(wanted, {"packages": []}, {"a": OSError(), "b": OSError(), "c": ("c", []), "d": ("d", [])})
        self.assertEqual(sorted(projects), ["c", "d"])


class Repology(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch("sys.stderr", io.StringIO()), mock.patch("time.sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def response(body, url="https://repology.org/api/v1/project/x"):
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = json.dumps(body).encode()
        resp.geturl.return_value = url
        return resp

    @staticmethod
    def http_error(code):
        return urllib.error.HTTPError("https://repology.org", code, "err", {}, None)

    def test_unknown_project_answers_empty_list_not_404(self):
        with mock.patch("urllib.request.urlopen", return_value=self.response([])):
            self.assertEqual(fetch.project_by_name("nope"), (None, None))

    def test_404_means_not_found(self):
        with mock.patch("urllib.request.urlopen", side_effect=self.http_error(404)):
            self.assertEqual(fetch.project_for_attr("nope"), (None, None))

    def test_project_name_taken_from_redirect(self):
        resp = self.response([nix("x", "1", "newest")], "https://repology.org/api/v1/project/python%3Arequests")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(fetch.project_for_attr("python313Packages.requests")[0], "python:requests")

    def test_retries_then_succeeds(self):
        with mock.patch.object(fetch, "BASE_URLS", ["https://a"]), \
             mock.patch("urllib.request.urlopen",
                        side_effect=[self.http_error(502), self.http_error(502), self.response(["ok"])]) as urlopen:
            self.assertEqual(fetch.repology_get("/x")[0], ["ok"])
            self.assertEqual(urlopen.call_count, 3)

    def test_gives_up_after_all_retries(self):
        with mock.patch.object(fetch, "BASE_URLS", ["https://a", "https://b"]), \
             mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")) as urlopen:
            with self.assertRaises(urllib.error.URLError):
                fetch.repology_get("/x")
            self.assertEqual(urlopen.call_count, 2 * (1 + len(fetch.RETRY_DELAYS)))


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

        with mock.patch.object(fetch, "GITHUB_SEARCH_BATCH", 4), \
             mock.patch.object(fetch, "github_token", return_value="t"), \
             mock.patch.object(fetch, "github_search_counts", side_effect=counts):
            fetch.add_github_counts(rows)
        self.assertEqual(seen, [4, 2])
        for row in rows:
            pr = f"repo:NixOS/nixpkgs is:pr state:open in:title {row['searchTerm']}"
            issue = f"repo:NixOS/nixpkgs is:issue state:open in:title {row['searchTerm']}"
            self.assertEqual((row["openPRs"], row["openIssues"]), (len(pr), len(issue) + 1))

    def test_no_token_skips_counts(self):
        rows = [{"searchTerm": "a"}]
        with mock.patch.object(fetch, "github_token", return_value=None):
            fetch.add_github_counts(rows)
        self.assertNotIn("openPRs", rows[0])

    def test_partial_graphql_answer(self):
        resp = Repology.response({"data": {"s0": {"issueCount": 3}, "s1": None},
                                  "errors": [{"message": "s1 failed"}]})
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(fetch.github_search_counts("t", ["q0", "q1"]), [3, None])

    def test_failed_request_blanks_its_batch(self):
        with mock.patch("urllib.request.urlopen", side_effect=Repology.http_error(401)):
            self.assertEqual(fetch.github_search_counts("t", ["q0", "q1"]), [None, None])


if __name__ == "__main__":
    unittest.main()
