"""Community update checks (nixkeeper/community.py): opting in, merging with
your own rules, and the limits that keep a contributed rule from doing harm
on subscribers' machines."""

import io
import os
import socket
import unittest
from unittest import mock

from nixkeeper import cli, community, config
from nixkeeper.sources import http, upstream

NOW = "2026-10-01T06:00:00+00:00"
CHROME = {
    "url": "https://versionhistory.googleapis.com/v1/chrome/versions",
    "pattern": r'"version": "([0-9.]+)"',
    "frequent": True,
}
WESNOTH = {"github": "wesnoth/wesnoth", "tags": r"^(1\.19\.[0-9]+)$"}
RULES = {"google-chrome": CHROME, "wesnoth-devel": WESNOTH, "untracked": CHROME}


class Merge(unittest.TestCase):
    def merge(self, lists, tracked=("google-chrome", "wesnoth-devel", "unciv")):
        with (
            mock.patch.object(community, "rules", return_value=RULES),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            return community.merge(lists, list(tracked))

    def test_off_unless_opted_in(self):
        own = {"unciv": {"github": "yairm210/Unciv", "tags": "^(.+)$"}}
        for lists in (
            {"updateChecks": own},
            {"updateChecks": own, "community": {"updateChecks": "yes"}},
            {"updateChecks": own, "community": {"ignoredUpdates": True}},
        ):
            with self.subTest(lists=lists):
                self.assertEqual(self.merge(lists), (own, set()))

    def test_only_for_tracked_packages(self):
        checks, names = self.merge({"community": {"updateChecks": True}})
        self.assertEqual(set(checks), {"google-chrome", "wesnoth-devel"})
        self.assertEqual(names, {"google-chrome", "wesnoth-devel"})

    def test_your_own_rule_wins(self):
        mine = {"github": "wesnoth/wesnoth", "tags": r"^(1\.20\.[0-9]+)$"}
        checks, names = self.merge(
            {
                "community": {"updateChecks": True},
                "updateChecks": {"wesnoth-devel": mine},
            }
        )
        self.assertEqual(checks["wesnoth-devel"], mine)
        self.assertEqual(names, {"google-chrome"})

    def test_the_shipped_file_is_found(self):
        self.assertTrue(os.path.exists(community.path()))


class MergeIgnores(unittest.TestCase):
    COMMUNITY = {"xskat": {"4.0-9": "never released"}, "egoboo": {"2.8.1": "tag only"}}

    def merge(self, lists, tracked=("xskat", "unciv")):
        with mock.patch.object(community, "ignores", return_value=self.COMMUNITY):
            return community.merge_ignores(lists, list(tracked))

    def test_off_unless_opted_in(self):
        own = {"unciv": {"4.0": "mine"}}
        for lists in (
            {"ignoredUpdates": own},
            {"ignoredUpdates": own, "community": {"updateChecks": True}},
        ):
            with self.subTest(lists=lists):
                self.assertEqual(self.merge(lists), (own, set()))

    def test_for_tracked_packages_your_reason_winning(self):
        lists = {
            "community": {"ignoredUpdates": True},
            "ignoredUpdates": {
                "xskat": {"4.0-9": "my reason"},
                "unciv": {"4.0": "mine"},
            },
        }
        merged, from_community = self.merge(lists)
        self.assertEqual(merged["xskat"], {"4.0-9": "my reason"})
        self.assertNotIn("egoboo", merged)  # not tracked
        self.assertEqual(from_community, set())

    def test_community_versions_added(self):
        lists = {"community": {"ignoredUpdates": True}}
        merged, from_community = self.merge(lists)
        self.assertEqual(merged, {"xskat": {"4.0-9": "never released"}})
        self.assertEqual(from_community, {("xskat", "4.0-9")})


class StaleIgnores(unittest.TestCase):
    RULES = {"xskat": {"4.0-9": "never released"}, "egoboo": {"2.8.1": "tag only"}}

    def stale(self, attempts, names=None):
        with (
            mock.patch.object(community, "ignores", return_value=self.RULES),
            mock.patch(
                "nixkeeper.sources.nixpkgs_update.latest_attempt",
                side_effect=lambda name: attempts[name],
            ),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            return community.stale_ignores(names)

    def test_a_rule_that_still_applies(self):
        found = self.stale(
            {
                "xskat": {"to": "4.0-9", "outcome": "failed"},
                "egoboo": {"to": "1", "was": "egoboo-2.8.1", "outcome": "failed"},
            }
        )
        self.assertEqual(found, {})

    def test_rules_that_can_go(self):
        found = self.stale(
            {"xskat": {"to": "4.1", "outcome": "failed"}, "egoboo": None}
        )
        self.assertEqual(
            found,
            {
                "xskat": [("4.0-9", "the bot's latest attempt is at 4.1")],
                "egoboo": [("2.8.1", "the bot has never tried this package")],
            },
        )
        # And when an updateScript attempt was at a newer version.
        moved = self.stale(
            {
                "xskat": {"to": "4.0-9", "outcome": "failed"},
                "egoboo": {"to": "1", "was": "egoboo-2.8.2", "outcome": "failed"},
            }
        )
        self.assertEqual(
            moved,
            {"egoboo": [("2.8.1", "the bot's latest attempt is at egoboo-2.8.2")]},
        )

    def test_a_log_that_cant_be_read_isnt_called_stale(self):
        def down(name):
            raise OSError("down")

        with (
            mock.patch.object(community, "ignores", return_value=self.RULES),
            mock.patch(
                "nixkeeper.sources.nixpkgs_update.latest_attempt", side_effect=down
            ),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            self.assertEqual(community.stale_ignores(), {})


class Limits(unittest.TestCase):
    def test_good_rules(self):
        for rule in (CHROME, WESNOTH, {"github": "a/b", "branch": "main"}):
            with self.subTest(rule=rule):
                self.assertIsNone(community.safety(rule))

    def test_refused(self):
        cases = {
            "http://example.org/v": "https",
            "https://127.0.0.1/v": "public host",
            "https://[::1]/v": "public host",
            "https://169.254.169.254/latest/meta-data": "public host",
            "https://localhost/v": "public host",
            "https://printer.local/v": "public host",
            "https://metadata.internal/v": "public host",
            "https://intranet/v": "public host",
            "https://example.org:8443/v": "port",
            "https://user:pw@example.org/v": "credentials",
        }
        for url, why in cases.items():
            with self.subTest(url=url):
                self.assertIn(why, community.safety({"url": url, "pattern": "x"}))

    def test_slow_or_long_patterns(self):
        for pattern in ("(a+)+$", r"(\w*)*x", "([0-9]+.)+", r"(a)\1", "x" * 201):
            with self.subTest(pattern=pattern):
                self.assertIsNotNone(
                    community.safety(
                        {"url": "https://example.org/", "pattern": pattern}
                    )
                )
        self.assertIsNone(community.safety({"github": "a/b", "tags": r"^v([0-9.]+)$"}))

    def test_only_known_fields(self):
        self.assertIn("unknown field", community.safety({**CHROME, "script": "x"}))
        self.assertIn("owner/repo", community.safety({"github": "../x", "tags": "x"}))


def resolving_to(*addresses):
    return mock.patch.object(
        socket,
        "getaddrinfo",
        return_value=[(socket.AF_INET, 0, 0, "", (a, 443)) for a in addresses],
    )


class SafeFetch(unittest.TestCase):
    def test_public_addresses_only(self):
        with resolving_to("93.184.216.34"):
            http.check_public("https://example.org/")
        for address in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1"):
            with (
                self.subTest(address=address),
                resolving_to("93.184.216.34", address),
                self.assertRaises(http.UnsafeURL),
            ):
                http.check_public("https://example.org/")

    def test_https_only(self):
        with self.assertRaises(http.UnsafeURL):
            http.check_public("http://example.org/")

    def test_redirects_are_checked_too(self):
        handler = http._CheckedRedirects()
        with resolving_to("10.0.0.5"), self.assertRaises(http.UnsafeURL):
            handler.redirect_request(None, None, 302, "Found", {}, "https://inside/")

    def test_size_cap(self):
        page = mock.MagicMock()
        page.__enter__.return_value.read.side_effect = lambda n: b"x" * n
        with (
            resolving_to("93.184.216.34"),
            mock.patch.object(http._safe_opener, "open", return_value=page),
            self.assertRaises(http.UnsafeURL),
        ):
            http.get("https://example.org/", safe=True)

    def test_unsafe_isnt_retried(self):
        with (
            resolving_to("10.0.0.5"),
            mock.patch("time.sleep") as sleep,
            self.assertRaises(http.UnsafeURL),
        ):
            http.get("https://example.org/", safe=True)
        sleep.assert_not_called()


class ForCI(unittest.TestCase):
    def test_problems(self):
        found = community.problems(
            {
                "fine": WESNOTH,
                "unsafe": {"url": "http://example.org/", "pattern": "x"},
                "broken": {"github": "a/b", "tags": "(unclosed"},
                "two-groups": {"github": "a/b", "tags": "(a)(b)"},
            }
        )
        self.assertEqual(len(found), 3)
        self.assertTrue(found[0].startswith("broken: tags is not a valid regex"))
        self.assertIn("two-groups: tags has more than one capture group", found)
        self.assertIn("unsafe: url must be https://", found)


class RunForReal(unittest.TestCase):
    """community-check: every rule, or some, against nixpkgs' versions."""

    def run_rules(self, names=None, page='{"version": "154.0.2"}'):
        index = {"google-chrome": {"version": "154.0.1"}}
        rules = {"google-chrome": CHROME, "not-in-nixpkgs": CHROME}
        with (
            mock.patch.object(community, "rules", return_value=rules),
            mock.patch("nixkeeper.sources.nixpkgs.load_index", return_value=index),
            mock.patch.object(http, "get", return_value=page),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            return community.run(names)

    def test_every_rule(self):
        results = self.run_rules()
        self.assertEqual(results["google-chrome"], ("154.0.2", None))
        self.assertEqual(
            results["not-in-nixpkgs"], (None, "not in nixpkgs' channel index")
        )

    def test_some_rules(self):
        results = self.run_rules(["google-chrome", "typo"])
        self.assertEqual(set(results), {"google-chrome", "typo"})
        self.assertEqual(results["typo"], (None, "no community rule of that name"))

    def test_a_rule_that_finds_nothing(self):
        version, why = self.run_rules(["google-chrome"], page="nothing here")[
            "google-chrome"
        ]
        self.assertIsNone(version)
        self.assertIn("nothing in", why)

    def test_report_counts_failures(self):
        with (
            mock.patch("sys.stdout", io.StringIO()),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            failed = community.report({"a": ("1.0", None), "b": (None, "moved")})
        self.assertEqual(failed, 1)


class CheckByName(unittest.TestCase):
    """`nixkeeper community-check NAME...`: each name is tried for the kinds
    of rule it has, update check or ignore rules, and a name with neither is
    reported (a typo)."""

    CHECKS = {"google-chrome": CHROME, "both": CHROME}
    IGNORES = {"xskat": {"4.0-9": "Never released."}, "both": {"2.0": "No."}}

    def check(self, *names):
        """(what it printed, whether it failed) for community-check names."""
        index = {"google-chrome": {"version": "154.0.1"}, "both": {"version": "1"}}
        attempts = {
            "xskat": {"to": "4.0-9", "outcome": "failed"},
            "both": {"to": "2.0", "outcome": "failed"},
        }
        out = io.StringIO()
        with (
            mock.patch.object(community, "rules", return_value=self.CHECKS),
            mock.patch.object(community, "ignores", return_value=self.IGNORES),
            mock.patch("nixkeeper.sources.nixpkgs.load_index", return_value=index),
            mock.patch.object(http, "get", return_value='{"version": "154.0.2"}'),
            mock.patch(
                "nixkeeper.sources.nixpkgs_update.latest_attempt",
                side_effect=lambda name: attempts.get(name),
            ),
            mock.patch.dict(os.environ, {}, clear=True),
            # The command sets these from its flags: put back after.
            mock.patch.object(config, "LISTS", config.LISTS),
            mock.patch.object(config, "OUT_DIR", config.OUT_DIR),
            mock.patch.object(config, "NOTIFY", config.NOTIFY),
            mock.patch("sys.stdout", out),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            try:
                cli.main(["community-check", *names])
                failed = False
            except SystemExit:
                failed = True
        return out.getvalue(), failed

    def test_an_update_check_only(self):
        out, failed = self.check("google-chrome")
        self.assertIn("google-chrome: 154.0.2", out)
        self.assertNotIn("ignore rules", out)  # it has none
        self.assertFalse(failed)

    def test_ignore_rules_only(self):
        out, failed = self.check("xskat")
        self.assertIn("ignore rules for xskat: still apply", out)
        self.assertNotIn("no community rule", out)  # not tried as an update check
        self.assertFalse(failed)

    def test_both_kinds(self):
        out, failed = self.check("both")
        self.assertIn("both: 154.0.2", out)
        self.assertIn("ignore rules for both: still apply", out)
        self.assertFalse(failed)

    def test_neither_is_a_typo(self):
        out, failed = self.check("google-chrome", "xskatt")
        self.assertIn("xskatt: no community rule of that name", out)
        self.assertNotIn("ignore rules", out)
        self.assertTrue(failed)


class StatusIssue(unittest.TestCase):
    """The weekly run's issue: which rules are broken, and since when."""

    NOW = "2026-10-05T07:41:00+00:00"

    def publish(self, results, body=None):
        env = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "iedame/nixkeeper"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("nixkeeper.sources.github.status_issue_body", return_value=body),
            mock.patch(
                "nixkeeper.sources.github.update_status_issue", return_value=7
            ) as update,
            mock.patch("sys.stderr", io.StringIO()),
        ):
            community.publish(results, now=self.NOW)
        repo, token, title, new_body, comment = update.call_args.args
        self.assertEqual(update.call_args.kwargs["label"], community.ISSUE_LABEL)
        return new_body, comment

    def test_all_working(self):
        body, comment = self.publish({"a": ("1.0", None), "b": ("2.0", None)})
        self.assertIn("All 2 work", body)
        self.assertIn("All still apply", body)
        self.assertIsNone(comment)

    def test_ignore_rules_that_can_go(self):
        stale = {"xskat": [("4.0-9", "the bot's latest attempt is at 4.1")]}
        env = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "iedame/nixkeeper"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("nixkeeper.sources.github.status_issue_body", return_value=None),
            mock.patch(
                "nixkeeper.sources.github.update_status_issue", return_value=7
            ) as update,
            mock.patch("sys.stderr", io.StringIO()),
        ):
            community.publish({"a": ("1.0", None)}, stale, now=self.NOW)
        body = update.call_args.args[3]
        self.assertIn("| `xskat` | 4.0-9 | the bot's latest attempt is at 4.1 |", body)

    def test_a_rule_breaks_then_stays_broken_then_recovers(self):
        body, comment = self.publish({"a": ("1.0", None), "b": (None, "moved")})
        self.assertIn("1 of 2 broken", body)
        self.assertIn("| `b` | 2026-10-05 | moved |", body)
        self.assertIn("**Broke:** `b`: moved", comment)
        # A week later, still broken: its date stays, and no new comment.
        self.NOW = "2026-10-12T07:41:00+00:00"
        body, comment = self.publish({"a": ("1.0", None), "b": (None, "moved")}, body)
        self.assertIn("| `b` | 2026-10-05 | moved |", body)
        self.assertIsNone(comment)
        # Then fixed.
        body, comment = self.publish({"a": ("1.0", None), "b": ("2.1", None)}, body)
        self.assertIn("All 2 work", body)
        self.assertEqual(comment, "**Works again:** `b`")

    def test_needs_an_explicit_token(self):
        with (
            mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r"}, clear=True),
            mock.patch("nixkeeper.sources.github.token", return_value=None),
            self.assertRaises(SystemExit),
        ):
            community.publish({}, now=self.NOW)

    def test_track_only_counts_rules_that_ran(self):
        previous = {"gone": {"since": "x", "reason": "y"}}
        broken, newly, recovered = community.track(
            {"a": ("1.0", None)}, previous, self.NOW
        )
        self.assertEqual((broken, newly, recovered), ({}, [], []))


class ChangedInAPullRequest(unittest.TestCase):
    def test_only_added_or_changed_rules(self):
        base_checks = {"google-chrome": CHROME, "wesnoth-devel": WESNOTH}
        head_checks = {
            "google-chrome": CHROME,
            "wesnoth-devel": {**WESNOTH, "tags": "^(1\\.20\\..+)$"},
            "new": CHROME,
        }
        base_ignores = {"xskat": {"4.0-9": "never released"}}
        head_ignores = {**base_ignores, "foo": {"1.2": "tagged by mistake"}}

        def read(file=None):
            if file is None:
                return head_checks
            if file.endswith(community.IGNORES):
                return base_ignores if file.startswith("main") else head_ignores
            return base_checks

        with (
            mock.patch.object(community, "rules", side_effect=read),
            mock.patch("os.path.exists", return_value=True),
        ):
            checks, ignored = community.changed("main")
        self.assertEqual(checks, ["new", "wesnoth-devel"])
        self.assertEqual(ignored, ["foo"])


class InTheChecks(unittest.TestCase):
    def setUp(self):
        out = mock.patch("sys.stderr", io.StringIO())
        out.start()
        self.addCleanup(out.stop)

    def rows(self):
        return [
            {"name": "google-chrome", "nixVersion": "154.0.1", "refVersion": "154.0.1"}
        ]

    def test_a_community_rule_is_fetched_safely_and_marked(self):
        rows = self.rows()
        page = '{"version": "154.0.2"}'
        with mock.patch.object(http, "get", return_value=page) as get:
            upstream.add_checks(
                rows,
                {"google-chrome": CHROME},
                {"packages": []},
                NOW,
                {"google-chrome"},
            )
        get.assert_called_once_with(CHROME["url"], safe=True)
        self.assertEqual(rows[0]["upstream"]["version"], "154.0.2")
        self.assertTrue(rows[0]["upstream"]["community"])

    def test_your_own_rule_isnt_held_to_the_limits(self):
        rows = self.rows()
        local = {"url": "http://192.168.1.10/versions", "pattern": "([0-9.]+)"}
        with mock.patch.object(http, "get", return_value="154.0.2") as get:
            upstream.add_checks(rows, {"google-chrome": local}, {"packages": []}, NOW)
        get.assert_called_once_with(local["url"], safe=False)
        self.assertNotIn("community", rows[0]["upstream"])

    def test_an_unsafe_community_rule_is_refused_unfetched(self):
        rows = self.rows()
        bad = {"url": "http://192.168.1.10/versions", "pattern": "([0-9.]+)"}
        with mock.patch.object(http, "get") as get:
            upstream.add_checks(
                rows, {"google-chrome": bad}, {"packages": []}, NOW, {"google-chrome"}
            )
        get.assert_not_called()
        self.assertIn(
            "community rule refused", rows[0]["notRefreshed"]["upstream"]["reason"]
        )


if __name__ == "__main__":
    unittest.main()
