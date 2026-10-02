"""How big a sync is, and its limits (nixkeeper/scale.py)."""

import io
import os
import tempfile
import unittest
from unittest import mock

from nixkeeper import listcheck, scale


class Estimate(unittest.TestCase):
    def test_durations_read_as_estimates(self):
        self.assertEqual(scale.duration(30), "about 1 min")
        self.assertEqual(scale.duration(7 * 60), "about 7 min")
        self.assertEqual(scale.duration(90 * 60), "about 1 h 30 min")
        self.assertEqual(scale.duration(121 * 60), "about 2 h")

    def test_describe(self):
        self.assertEqual(
            scale.describe(500),
            "500 packages: a sync takes about 1 h and makes about 4,000 "
            "requests to public services",
        )


class Limit(unittest.TestCase):
    def test_default_and_raised(self):
        self.assertEqual(scale.limit({}), scale.MAX_PACKAGES)
        self.assertEqual(scale.limit({"maxPackages": 3000}), 3000)

    def test_only_a_positive_whole_number_raises_it(self):
        for value in (None, 0, -5, "3000", 2.5, True):
            with self.subTest(value=value):
                self.assertEqual(
                    scale.limit({"maxPackages": value}), scale.MAX_PACKAGES
                )


class Check(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        self.stderr = patcher.start()
        self.addCleanup(patcher.stop)

    def test_says_how_long_it_takes(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            scale.check({}, 47)
        self.assertIn(
            "Tracking 47 packages: a sync takes about 6 min", self.stderr.getvalue()
        )

    def test_and_in_the_github_summary(self):
        with tempfile.NamedTemporaryFile("r") as summary:
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary.name}):
                scale.check({}, 47)
            self.assertIn("Tracking 47 packages", summary.read())

    def test_refuses_past_the_limit(self):
        with self.assertRaises(SystemExit) as stop:
            scale.check({}, 2001)
        self.assertIn("maxPackages = 2001;", str(stop.exception.code))

    def test_unless_the_lists_raise_it(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            scale.check({"maxPackages": 2500}, 2001)  # no exit


class ListCheck(unittest.TestCase):
    def problems(self, lists, count):
        tracked = [f"p{i}" for i in range(count)]
        return listcheck.problems({"maintainers": [], **lists}, {}, tracked)

    def test_warns_from_500(self):
        self.assertEqual(self.problems({}, 499), [])
        found = self.problems({}, 500)
        self.assertEqual(len(found), 1)
        self.assertIn("500 packages", found[0])

    def test_a_bad_limit(self):
        self.assertIn(
            "maxPackages: 'lots' isn't a positive whole number (using 2,000)",
            self.problems({"maxPackages": "lots"}, 1),
        )
