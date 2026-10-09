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

    def test_its_slot_day_once(self):
        when = datetime.fromisoformat(NOW)
        on_slot = next(
            n for n in (f"pkg{i}" for i in range(100)) if schedule.slot(n, when)
        )
        earlier_today = (when - timedelta(hours=3)).isoformat()
        self.assertFalse(schedule.due(on_slot, earlier_today, NOW))

    def test_daily(self):
        when = datetime.fromisoformat(NOW)
        self.assertTrue(schedule.daily(None, NOW))
        self.assertFalse(schedule.daily((when - timedelta(hours=3)).isoformat(), NOW))
        self.assertFalse(schedule.daily((when - timedelta(hours=21)).isoformat(), NOW))
        self.assertTrue(schedule.daily((when - timedelta(hours=22)).isoformat(), NOW))

    def test_syncs_every_three_hours_ask_as_a_daily_one(self):
        """Over 3 days of syncs every 3 hours: something quiet asked at most
        once a day (its slot day once, or once QUIET_DAYS have passed), not at
        every sync of it; something going on once a day."""
        start = datetime.fromisoformat("2026-10-05T00:30:00+00:00")
        quiet_asked, daily_asked = [], []
        quiet_at = daily_at = (start - timedelta(days=1)).isoformat()
        for k in range(24):
            now = (start + timedelta(hours=3 * k)).isoformat()
            if schedule.due("pkg7", quiet_at, now):
                quiet_asked.append(now)
                quiet_at = now
            if schedule.daily(daily_at, now):
                daily_asked.append(now)
                daily_at = now
        days = [a[:10] for a in quiet_asked]
        self.assertTrue(1 <= len(quiet_asked) <= 2, quiet_asked)
        self.assertEqual(len(days), len(set(days)))  # never twice in a day
        self.assertEqual(len(daily_asked), 3)
