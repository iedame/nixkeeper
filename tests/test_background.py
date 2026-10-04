"""Running a source in the background (nixkeeper/background.py)."""

import threading
import unittest

from nixkeeper.background import Background


class Background_(unittest.TestCase):
    def test_runs_at_once_and_gives_its_result(self):
        started = threading.Event()

        def work(a, b):
            started.set()
            return a + b

        job = Background(work, 2, 3)
        self.assertTrue(started.wait(5))  # without anyone asking for the result
        self.assertEqual(job.result(), 5)
        self.assertTrue(job.done())

    def test_runs_alongside(self):
        # The background waits for the caller: they run at the same time.
        go = threading.Event()
        job = Background(lambda: go.wait(5))
        self.assertFalse(job.done())
        go.set()
        self.assertTrue(job.result())

    def test_raises_what_it_raised(self):
        def work():
            raise ValueError("no")

        job = Background(work)
        with self.assertRaisesRegex(ValueError, "no"):
            job.result()

    def test_doesnt_hold_up_an_early_exit(self):
        job = Background(threading.Event().wait)
        self.assertTrue(job._thread.daemon)
