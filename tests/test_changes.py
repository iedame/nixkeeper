import unittest

from nixkeeper.changes import diff, should_notify


def row(name, status="newest", **extra):
    return {"name": name, "nixStatus": status, "nixVersion": "1", **extra}


class Diff(unittest.TestCase):
    def changes(self, before, now):
        return diff({"packages": before}, now)

    def test_newly_outdated_notifies(self):
        c = self.changes([row("unciv")], [row("unciv", "outdated")])
        self.assertEqual([r["name"] for r in c["outdated"]], ["unciv"])
        self.assertTrue(should_notify(c))

    def test_still_outdated_is_not_news(self):
        c = self.changes([row("unciv", "outdated")], [row("unciv", "legacy")])
        self.assertEqual(c["outdated"], [])
        self.assertFalse(should_notify(c))

    def test_caught_up_is_quiet(self):
        c = self.changes([row("unciv", "outdated")], [row("unciv")])
        self.assertEqual([r["name"] for r in c["caughtUp"]], ["unciv"])
        self.assertFalse(should_notify(c))

    def test_newly_failed(self):
        for now in (
            row("x", "missing"),
            row("x", buildFailure=True),
            row("x", updateFailure=True),
        ):
            with self.subTest(now=now):
                self.assertTrue(should_notify(self.changes([row("x")], [now])))
        # Still failing, for another reason: not new.
        self.assertFalse(
            should_notify(
                self.changes(
                    [row("x", "missing")], [row("x", "missing", buildFailure=True)]
                )
            )
        )

    def test_newly_vulnerable(self):
        c = self.changes([row("x")], [row("x", nixVulnerable=True)])
        self.assertEqual([r["name"] for r in c["vulnerable"]], ["x"])

    def test_not_refreshed_notifies_once(self):
        self.assertTrue(
            should_notify(self.changes([row("x")], [row("x", staleSince="2026-09-20")]))
        )
        self.assertFalse(
            should_notify(
                self.changes(
                    [row("x", staleSince="2026-09-20")],
                    [row("x", staleSince="2026-09-20")],
                )
            )
        )

    def test_added_and_removed_are_quiet(self):
        c = self.changes([row("old")], [row("new", "outdated")])
        self.assertEqual([r["name"] for r in c["added"]], ["new"])
        self.assertEqual(c["removed"], ["old"])
        self.assertEqual(c["outdated"], [])  # newly tracked, already outdated: not news
        self.assertFalse(should_notify(c))

    def test_first_run_notifies_nothing(self):
        c = self.changes([], [row("a", "outdated"), row("b", "missing")])
        self.assertFalse(should_notify(c))
