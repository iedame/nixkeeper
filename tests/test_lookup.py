import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from nixkeeper.history import load_previous_run
from nixkeeper.lookup import collect_projects
from tests.helpers import nix


class CollectProjects(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.known = {}  # fallback name -> the known project resolve was given

    def write_previous(
        self, packages, checked_at="2026-09-20T06:00:00+00:00", files=None
    ):
        with open(os.path.join(self.dir.name, "index.json"), "w") as f:
            json.dump({"checkedAt": checked_at, "packages": packages}, f)
        for name, entries in (files or {}).items():
            with open(os.path.join(self.dir.name, name), "w") as f:
                json.dump(entries, f)
        return load_previous_run(self.dir.name)

    def collect(self, wanted, previous, answers):
        """answers: fallback name -> (project, entries), or an exception."""

        def resolve(fallback, attrs, known=None):
            self.known[fallback] = known
            answer = answers[fallback]
            if isinstance(answer, Exception):
                raise answer
            return answer

        return collect_projects(wanted, previous, resolve, self.dir.name)

    def test_attrs_resolving_to_one_project_merge(self):
        entries = [nix("wesnoth", "1.18.8", "newest")]
        projects = self.collect(
            {
                "wesnoth": (["wesnoth"], "wesnoth"),
                "wesnoth-devel": (["wesnoth-devel"], "wesnoth-devel"),
            },
            {"packages": []},
            {"wesnoth": ("wesnoth", entries), "wesnoth-devel": ("wesnoth", entries)},
        )
        self.assertEqual(list(projects), ["wesnoth"])
        self.assertEqual(projects["wesnoth"]["attrs"], ["wesnoth", "wesnoth-devel"])

    def test_the_last_runs_project_is_passed_on(self):
        previous = {
            "packages": [
                {"name": "wesnoth", "project": "wesnoth", "attrs": ["wesnoth"]},
                {"name": "nope", "project": None, "attrs": []},
            ]
        }
        entries = [nix("wesnoth", "1.18.8", "newest")]
        self.collect(
            {
                "wesnoth": (["wesnoth"], "wesnoth"),
                "unciv": (["unciv"], "unciv"),
                "nope": ([], "nope"),
            },
            previous,
            {
                "wesnoth": ("wesnoth", entries),
                "unciv": ("unciv", [nix("unciv", "4", "newest")]),
                "nope": (None, None),
            },
        )
        self.assertEqual(
            self.known, {"wesnoth": "wesnoth", "unciv": None, "nope": None}
        )

    def test_unknown_to_repology_keyed_by_name(self):
        projects = self.collect(
            {"nope": ([], "nope")}, {"packages": []}, {"nope": (None, None)}
        )
        self.assertEqual(projects["nope"]["project"], None)
        self.assertEqual(projects["nope"]["entries"], [])

    def test_failed_lookup_reuses_previous_data(self):
        entries = [nix("wesnoth", "1.18.8", "newest")]
        previous = self.write_previous(
            [
                {
                    "name": "wesnoth",
                    "searchTerm": "wesnoth",
                    "attrs": ["wesnoth"],
                    "project": "wesnoth",
                    "dataFile": "wesnoth.json",
                }
            ],
            files={"wesnoth.json": entries},
        )
        projects = self.collect(
            {
                "wesnoth": (["wesnoth"], "wesnoth"),
                "bbedit": (["bbedit"], "bbedit"),
                "fzssh": (["fzssh"], "fzssh"),
            },
            previous,
            {
                "wesnoth": urllib.error.URLError("down"),
                "bbedit": ("bbedit", []),
                "fzssh": ("fzssh", []),
            },
        )
        self.assertEqual(projects["wesnoth"]["entries"], entries)
        self.assertEqual(projects["wesnoth"]["staleSince"], "2026-09-20T06:00:00+00:00")
        self.assertNotIn("staleSince", projects["bbedit"])

    def test_repeated_failure_keeps_original_date(self):
        previous = self.write_previous(
            [
                {
                    "name": "wesnoth",
                    "attrs": ["wesnoth"],
                    "project": "wesnoth",
                    "dataFile": "wesnoth.json",
                    "staleSince": "2026-09-01T06:00:00+00:00",
                }
            ],
            files={"wesnoth.json": []},
        )
        projects = self.collect(
            {
                "wesnoth": (["wesnoth"], "wesnoth"),
                "bbedit": (["bbedit"], "bbedit"),
                "fzssh": (["fzssh"], "fzssh"),
            },
            previous,
            {
                "wesnoth": OSError("down"),
                "bbedit": ("bbedit", []),
                "fzssh": ("fzssh", []),
            },
        )
        self.assertEqual(projects["wesnoth"]["staleSince"], "2026-09-01T06:00:00+00:00")

    def test_failed_lookup_without_previous_data_is_skipped(self):
        projects = self.collect(
            {
                "new": (["new"], "new"),
                "bbedit": (["bbedit"], "bbedit"),
                "fzssh": (["fzssh"], "fzssh"),
            },
            {"packages": []},
            {"new": OSError("down"), "bbedit": ("bbedit", []), "fzssh": ("fzssh", [])},
        )
        self.assertEqual(sorted(projects), ["bbedit", "fzssh"])

    def test_more_than_half_failing_aborts(self):
        wanted = {n: ([n], n) for n in "abc"}
        with self.assertRaises(SystemExit):
            self.collect(
                wanted,
                {"packages": []},
                {"a": OSError(), "b": OSError(), "c": ("c", [])},
            )

    def test_exactly_half_failing_continues(self):
        wanted = {n: ([n], n) for n in "abcd"}
        projects = self.collect(
            wanted,
            {"packages": []},
            {"a": OSError(), "b": OSError(), "c": ("c", []), "d": ("d", [])},
        )
        self.assertEqual(sorted(projects), ["c", "d"])
