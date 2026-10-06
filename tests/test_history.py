import json
import os
import tempfile
import unittest

from nixkeeper.history import add_outdated_since, new_packages, previous_project


class OutdatedSince(unittest.TestCase):
    NOW = "2026-09-28T06:00:00+00:00"

    def run_with(self, status, previous_row=None):
        row = {"name": "unciv", "nixStatus": status}
        add_outdated_since(
            [row], {"packages": [previous_row] if previous_row else []}, self.NOW
        )
        return row.get("outdatedSince")

    def test_newly_outdated_starts_now(self):
        self.assertEqual(
            self.run_with("outdated", {"name": "unciv", "nixStatus": "newest"}),
            self.NOW,
        )
        self.assertEqual(self.run_with("outdated"), self.NOW)  # new package

    def test_still_outdated_keeps_date_even_after_an_update(self):
        before = {
            "name": "unciv",
            "nixStatus": "outdated",
            "nixVersion": "4.22.1",
            "outdatedSince": "2026-09-01T06:00:00+00:00",
        }
        self.assertEqual(self.run_with("outdated", before), "2026-09-01T06:00:00+00:00")

    def test_an_older_version_kept_isnt_outdated(self):
        # Repology's "legacy": nixpkgs keeps it beside a newer one.
        self.assertIsNone(self.run_with("legacy"))

    def test_caught_up_drops_the_date(self):
        before = {
            "name": "unciv",
            "nixStatus": "outdated",
            "outdatedSince": "2026-09-01T06:00:00+00:00",
        }
        self.assertIsNone(self.run_with("newest", before))

    def test_outdated_before_tracking_started_starts_now(self):
        # Rows from runs before this feature have no date yet.
        self.assertEqual(
            self.run_with("outdated", {"name": "unciv", "nixStatus": "outdated"}),
            self.NOW,
        )


class PreviousProject(unittest.TestCase):
    """A failed Repology lookup reuses the last run's file for the project."""

    def test_a_file_from_before_trimming_comes_back_trimmed(self):
        full = {
            "repo": "arch",
            "srcname": "unciv",
            "binname": "unciv",
            "version": "4.22.6",
            "status": "newest",
            "summary": "Civ V clone",
        }
        previous = {
            "checkedAt": "2026-10-03T06:00:00+00:00",
            "packages": [
                {"name": "unciv", "project": "unciv", "dataFile": "unciv.json"}
            ],
        }
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "unciv.json"), "w") as f:
                json.dump([full, {**full, "binname": "unciv-doc"}], f)
            project, entries, since = previous_project(
                previous, "unciv", ["unciv"], out
            )
        self.assertEqual(project, "unciv")
        self.assertEqual(
            entries,
            [
                {
                    "repo": "arch",
                    "srcname": "unciv",
                    "version": "4.22.6",
                    "status": "newest",
                }
            ],
        )
        self.assertEqual(since, "2026-10-03T06:00:00+00:00")


class NewPackages(unittest.TestCase):
    """How many tracked packages the last run didn't have (the estimate's
    expensive ones)."""

    def test_by_name_or_attribute(self):
        previous = {
            "packages": [
                {"name": "wesnoth", "attrs": ["wesnoth"]},
                {
                    "name": "heroic",
                    "searchTerm": "heroic",
                    "attrs": ["heroic-unwrapped"],
                },
            ]
        }
        wanted = {
            "wesnoth": (["wesnoth"], "wesnoth"),  # by name
            "heroic-unwrapped": (["heroic-unwrapped"], "heroic"),  # by attribute
            "unciv": (["unciv"], "unciv"),  # new
            "gone": ([], "gone"),  # new, not in nixpkgs
        }
        self.assertEqual(new_packages(previous, wanted), 2)
        self.assertEqual(new_packages({"packages": []}, wanted), 4)
