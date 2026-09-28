import unittest

from nixkeeper.history import add_outdated_since


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

    def test_legacy_counts_as_outdated(self):
        self.assertEqual(self.run_with("legacy"), self.NOW)

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
