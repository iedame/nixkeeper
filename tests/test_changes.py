import unittest

from nixkeeper.changes import (
    count_master,
    diff,
    failures,
    is_outdated,
    should_notify,
    waiting_for_channel,
)


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
        c = self.changes([row("unciv", "outdated")], [row("unciv", "outdated")])
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


class OlderVersionKept(unittest.TestCase):
    """Repology's "legacy": an older version nixpkgs keeps beside a newer one
    under another attribute. Outdated only by a newer release in its own
    series, or, for a devel variant, a newer devel version elsewhere."""

    def test_not_outdated_by_itself(self):
        self.assertFalse(is_outdated(row("tracy_0_11", "legacy", refVersion="0.14.1")))

    def test_a_newer_release_in_its_series(self):
        newer = {"version": "1.1", "newer": True, "inferred": True}
        self.assertTrue(is_outdated(row("tracy_0_11", "legacy", upstream=newer)))

    def test_a_devel_variant_behind_other_devel_versions(self):
        beta = row("foo-beta", "legacy", devel=True, refVersion="2")
        self.assertTrue(is_outdated(beta))
        # Ahead of the devel versions elsewhere: kept beside the stable one.
        self.assertFalse(is_outdated({**beta, "refVersion": "0.9"}))


class MasterAhead(unittest.TestCase):
    """Hydra's master build newer than the channel: a newer release exists,
    whatever Repology and the update checks know."""

    def test_counts_as_outdated(self):
        self.assertTrue(is_outdated(row("x", master="2")))
        self.assertFalse(is_outdated(row("x", master="1")))  # same as the channel
        self.assertFalse(is_outdated(row("x", master="0.9")))
        self.assertFalse(is_outdated(row("x")))

    def test_master_becomes_the_version_to_update_to(self):
        r = row("wesnoth-devel", "devel", nixVersion="1.19.24", refVersion="1.19.24")
        r["master"] = "1.19.28"
        count_master(r)
        self.assertEqual(r["refVersion"], "1.19.28")
        self.assertTrue(r["refFromMaster"])
        self.assertTrue(waiting_for_channel(r))

    def test_a_newer_known_release_stays(self):
        # unciv: master has 4.22.5, but 4.22.6 is out: still to do.
        r = row("unciv", "outdated", nixVersion="4.22.1", refVersion="4.22.6")
        r["master"] = "4.22.5"
        count_master(r)
        self.assertEqual(r["refVersion"], "4.22.6")
        self.assertNotIn("refFromMaster", r)
        self.assertFalse(waiting_for_channel(r))

    def test_once_the_channel_catches_up(self):
        r = row("x", nixVersion="2", refVersion="2", master="2", refFromMaster=True)
        count_master(r)
        self.assertNotIn("refFromMaster", r)
        self.assertFalse(is_outdated(r))


class WaitingForChannel(unittest.TestCase):
    """Outdated with the update already on master: merged, waiting for
    nixos-unstable."""

    def outdated(self, **extra):
        return row("wesnoth-devel", "outdated", refVersion="1.19.28", **extra)

    def test_waiting(self):
        self.assertTrue(waiting_for_channel(self.outdated(master="1.19.28")))
        self.assertTrue(waiting_for_channel(self.outdated(master="1.19.29")))
        # master ahead of the channel, but not yet at the newest: still to do.
        self.assertFalse(waiting_for_channel(self.outdated(master="1.19.26")))
        self.assertFalse(waiting_for_channel(self.outdated()))
        self.assertFalse(waiting_for_channel(row("x")))  # not outdated
        # Master ahead of a channel Repology calls newest: outdated, merged.
        self.assertTrue(waiting_for_channel(row("x", master="2")))

    def test_master_ahead_is_not_newly_outdated_news(self):
        before = {"packages": [row("wesnoth-devel", "devel", refVersion="1")]}
        now = row("wesnoth-devel", "devel", refVersion="1", master="1.1")
        count_master(now)
        self.assertEqual(diff(before, [now])["outdated"], [])

    def test_not_newly_outdated_news(self):
        before = {"packages": [row("wesnoth-devel")]}
        c = diff(before, [self.outdated(master="1.19.28")])
        self.assertEqual(c["outdated"], [])
        c = diff(before, [self.outdated()])
        self.assertEqual([r["name"] for r in c["outdated"]], ["wesnoth-devel"])
