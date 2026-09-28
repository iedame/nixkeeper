import unittest

from nixkeeper.changes import diff, failures, should_notify


def row(name, status="newest", **extra):
    return {"name": name, "nixStatus": status, "nixVersion": "1", **extra}


def build(attr, system, status, build_id=1):
    return {"attr": attr, "system": system, "status": status, "build": build_id}


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
            row("x", builds=[build("x", "aarch64-darwin", "failed")]),
            row("x", updateFailure=True),
        ):
            with self.subTest(now=now):
                self.assertTrue(should_notify(self.changes([row("x")], [now])))

    def test_failing_on_another_platform_notifies(self):
        darwin = build("x", "aarch64-darwin", "failed")
        linux = build("x", "x86_64-linux", "failed")
        self.assertTrue(
            should_notify(
                self.changes(
                    [row("x", builds=[darwin])], [row("x", builds=[darwin, linux])]
                )
            )
        )
        # Same failures (a new build id doesn't matter): not news.
        again = {**darwin, "build": 2}
        self.assertFalse(
            should_notify(
                self.changes([row("x", builds=[darwin])], [row("x", builds=[again])])
            )
        )

    def test_only_the_package_own_failures_count(self):
        for status in ("dependency", "unfinished", "notBuilt", "unknown"):
            with self.subTest(status=status):
                c = self.changes(
                    [row("x")], [row("x", builds=[build("x", "x86_64-linux", status)])]
                )
                self.assertFalse(should_notify(c))

    def test_fixed_is_quiet(self):
        c = self.changes(
            [row("x", builds=[build("x", "x86_64-linux", "failed")])],
            [row("x", builds=[build("x", "x86_64-linux", "ok")])],
        )
        self.assertEqual([r["name"] for r in c["fixed"]], ["x"])
        self.assertFalse(should_notify(c))

    def test_marked_broken_is_quiet_and_not_a_failure(self):
        broken = row("x", builds=[build("x", "aarch64-darwin", "broken")])
        self.assertEqual(failures(broken), [])
        c = self.changes([row("x")], [broken])
        self.assertEqual([r["name"] for r in c["broken"]], ["x"])
        self.assertFalse(should_notify(c))
        # Once is enough.
        self.assertEqual(self.changes([broken], [broken])["broken"], [])

    def test_failure_marked_broken_is_not_fixed(self):
        c = self.changes(
            [row("x", builds=[build("x", "aarch64-darwin", "failed")])],
            [row("x", builds=[build("x", "aarch64-darwin", "broken")])],
        )
        self.assertEqual([r["name"] for r in c["broken"]], ["x"])
        self.assertEqual(c["fixed"], [])

    def test_failure_names_other_attrs(self):
        r = row("heroic", attrs=["heroic", "heroic-unwrapped"])
        r["builds"] = [build("heroic-unwrapped", "x86_64-linux", "failed")]
        self.assertEqual(
            failures(r), ["build failure on heroic-unwrapped on x86_64-linux"]
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

    def test_each_source_not_refreshing_notifies_once(self):
        hydra = {"builds": {"since": "2026-09-29", "reason": "down"}}
        both = {**hydra, "upstream": {"since": "2026-09-30", "reason": "404"}}
        c = self.changes([row("x")], [row("x", notRefreshed=hydra)])
        self.assertTrue(should_notify(c))
        # Still failing: not news. Another source failing too: news.
        self.assertFalse(
            should_notify(
                self.changes(
                    [row("x", notRefreshed=hydra)], [row("x", notRefreshed=hydra)]
                )
            )
        )
        c = self.changes([row("x", notRefreshed=hydra)], [row("x", notRefreshed=both)])
        self.assertEqual([r["name"] for r in c["notRefreshed"]], ["x"])

    def test_refreshed_again_is_quiet(self):
        hydra = {"builds": {"since": "2026-09-29", "reason": "down"}}
        c = self.changes([row("x", notRefreshed=hydra)], [row("x")])
        self.assertEqual([r["name"] for r in c["refreshed"]], ["x"])
        self.assertFalse(should_notify(c))

    def test_added_and_removed_are_quiet(self):
        c = self.changes([row("old")], [row("new", "outdated")])
        self.assertEqual([r["name"] for r in c["added"]], ["new"])
        self.assertEqual(c["removed"], ["old"])
        self.assertEqual(c["outdated"], [])  # newly tracked, already outdated: not news
        self.assertFalse(should_notify(c))

    def test_first_run_notifies_nothing(self):
        c = self.changes([], [row("a", "outdated"), row("b", "missing")])
        self.assertFalse(should_notify(c))
