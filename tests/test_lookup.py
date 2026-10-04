import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

from nixkeeper import schedule
from nixkeeper.history import load_previous_run
from nixkeeper.lookup import collect_projects
from nixkeeper.rows import build_rows
from tests.helpers import nix, other


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


class QuietLookups(unittest.TestCase):
    """Packages with nothing going on are looked up on Repology every
    QUIET_DAYS (schedule.py), keeping the last run's data in between."""

    NOW = "2026-10-05T06:00:00+00:00"

    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def not_its_day(self, name="unciv"):
        when = datetime.fromisoformat(self.NOW)
        while schedule.slot(name, when):
            when += timedelta(days=1)
        return when.isoformat()

    def previous(self, now, **row):
        """unciv as a sync a day before now left it, with its Repology file."""
        entries = [nix("unciv", "4.22.1", "newest"), other("arch", "4.22.1", "newest")]
        with open(os.path.join(self.dir.name, "unciv.json"), "w") as f:
            json.dump(entries, f)
        checked = (datetime.fromisoformat(now) - timedelta(days=1)).isoformat()
        return {
            "packages": [
                {
                    "name": "unciv",
                    "attrs": ["unciv"],
                    "project": "unciv",
                    "dataFile": "unciv.json",
                    "nixVersion": "4.22.1",
                    "nixStatus": "newest",
                    "repologyCheckedAt": checked,
                    **row,
                }
            ]
        }

    def collect(self, previous, now, version="4.22.1", wanted=None):
        """(projects, the pnames looked up)."""
        asked = []
        fresh = [nix("unciv", version, "newest"), other("arch", "4.22.6", "newest")]

        def resolve(fallback, attrs, known=None):
            asked.append(fallback)
            return "unciv", fresh

        nixpkgs = {
            "unciv": {"version": version},
            "unciv-unwrapped": {"version": version},
        }
        projects = collect_projects(
            wanted or {"unciv": (["unciv"], "unciv")},
            previous,
            resolve,
            self.dir.name,
            nixpkgs=nixpkgs,
            now=now,
        )
        return projects, asked

    def test_nothing_going_on_isnt_looked_up(self):
        now = self.not_its_day()
        previous = self.previous(now)
        projects, asked = self.collect(previous, now)
        self.assertEqual(asked, [])
        unciv = projects["unciv"]
        self.assertEqual(
            unciv["checkedAt"], previous["packages"][0]["repologyCheckedAt"]
        )
        self.assertEqual([e["version"] for e in unciv["entries"]], ["4.22.1", "4.22.1"])
        self.assertNotIn("staleSince", unciv)

    def test_something_going_on_is_looked_up(self):
        now = self.not_its_day()
        for name, row, version in (
            ("never dated", {"repologyCheckedAt": None}, "4.22.1"),
            ("failed last time", {"staleSince": now}, "4.22.1"),
            ("outdated", {"nixStatus": "outdated"}, "4.22.1"),
            ("vulnerable", {"nixVulnerable": True}, "4.22.1"),
            ("nixpkgs moved", {}, "4.22.5"),
        ):
            with self.subTest(name):
                projects, asked = self.collect(self.previous(now, **row), now, version)
                self.assertEqual(asked, ["unciv"])
                self.assertEqual(projects["unciv"]["checkedAt"], now)

    def test_new_packages_are_looked_up(self):
        _, asked = self.collect({"packages": []}, self.NOW)
        self.assertEqual(asked, ["unciv"])

    def test_three_days_on_it_is_looked_up(self):
        now = self.not_its_day()
        checked = (datetime.fromisoformat(now) - timedelta(days=3)).isoformat()
        _, asked = self.collect(self.previous(now, repologyCheckedAt=checked), now)
        self.assertEqual(asked, ["unciv"])

    def test_without_its_file_its_looked_up(self):
        now = self.not_its_day()
        previous = self.previous(now)
        os.remove(os.path.join(self.dir.name, "unciv.json"))
        _, asked = self.collect(previous, now)
        self.assertEqual(asked, ["unciv"])

    def test_one_project_takes_its_freshest_lookup(self):
        # unciv quiet, unciv-unwrapped new: the same project, looked up fresh.
        now = self.not_its_day()
        projects, asked = self.collect(
            self.previous(now),
            now,
            wanted={
                "unciv": (["unciv"], "unciv"),
                "unciv-unwrapped": (["unciv-unwrapped"], "unciv-unwrapped"),
            },
        )
        self.assertEqual(asked, ["unciv-unwrapped"])
        unciv = projects["unciv"]
        self.assertEqual(unciv["attrs"], ["unciv", "unciv-unwrapped"])
        self.assertEqual(unciv["checkedAt"], now)
        self.assertIn("4.22.6", [e["version"] for e in unciv["entries"]])

    def test_without_the_time_everything_is_looked_up(self):
        # As before the schedule (and in community-check).
        previous = self.previous(self.NOW)
        asked = []

        def resolve(fallback, attrs, known=None):
            asked.append(fallback)
            return "unciv", []

        collect_projects(
            {"unciv": (["unciv"], "unciv")}, previous, resolve, self.dir.name
        )
        self.assertEqual(asked, ["unciv"])

    def test_rows_say_when(self):
        projects, _ = self.collect({"packages": []}, self.NOW)
        (row,) = build_rows(projects, {})
        self.assertEqual(row["repologyCheckedAt"], self.NOW)
