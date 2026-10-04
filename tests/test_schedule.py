"""Asking less about what's quiet (nixkeeper/schedule.py)."""

import unittest
from datetime import datetime, timedelta

from nixkeeper import schedule

NOW = "2026-10-05T06:00:00+00:00"


class Schedule(unittest.TestCase):
    def test_a_third_each_day_each_once(self):
        names = [f"pkg{i}" for i in range(3000)]
        start = datetime.fromisoformat(NOW)
        per_day = [
            sum(schedule.slot(n, start + timedelta(days=d)) for n in names)
            for d in range(3)
        ]
        self.assertEqual(sum(per_day), 3000)
        for n in per_day:
            self.assertAlmostEqual(n / 3000, 1 / 3, delta=0.03)

    def test_due(self):
        when = datetime.fromisoformat(NOW)
        name = next(
            n for n in (f"pkg{i}" for i in range(100)) if not schedule.slot(n, when)
        )

        def ago(**since):
            return (when - timedelta(**since)).isoformat()

        self.assertTrue(schedule.due(name, None, NOW))  # never checked
        self.assertFalse(schedule.due(name, ago(days=1), NOW))
        self.assertFalse(schedule.due(name, ago(days=2), NOW))
        self.assertTrue(schedule.due(name, ago(days=2, hours=19), NOW))
        self.assertTrue(schedule.due(name, ago(days=3), NOW))
        on_slot = next(
            n for n in (f"pkg{i}" for i in range(100)) if schedule.slot(n, when)
        )
        self.assertTrue(schedule.due(on_slot, ago(hours=20), NOW))
