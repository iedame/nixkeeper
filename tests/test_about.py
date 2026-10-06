"""What the sync's sources were (sources/about.py), for the manifest."""

import unittest

from nixkeeper.sources import about


class About(unittest.TestCase):
    def setUp(self):
        about.taken()  # nothing left from another test

    def test_noted_then_taken_once(self):
        about.note("updates", True, at="2026-10-05T15:00:00+00:00", pending=None)
        about.note("hydra", False, "too old", eval=1829803)
        self.assertEqual(
            about.taken(),
            {
                "hydra": {"used": False, "why": "too old", "eval": 1829803},
                "updates": {"used": True, "at": "2026-10-05T15:00:00+00:00"},
            },
        )
        self.assertEqual(about.taken(), {})

    def test_a_long_reason_is_cut(self):
        about.note("versions", False, "x" * 500)
        why = about.taken()["versions"]["why"]
        self.assertEqual(len(why), about.WHY_LENGTH)
        self.assertTrue(why.endswith("…"))
