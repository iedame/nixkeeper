"""Community update checks (nixkeeper/community.py): opting in, merging with
your own rules, and the limits that keep a contributed rule from doing harm
on subscribers' machines."""

import io
import os
import socket
import unittest
from unittest import mock

from nixkeeper import community
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
            {"updateChecks": own, "communityChecks": "yes"},
        ):
            with self.subTest(lists=lists):
                self.assertEqual(self.merge(lists), (own, set()))

    def test_only_for_tracked_packages(self):
        checks, names = self.merge({"communityChecks": True})
        self.assertEqual(set(checks), {"google-chrome", "wesnoth-devel"})
        self.assertEqual(names, {"google-chrome", "wesnoth-devel"})

    def test_your_own_rule_wins(self):
        mine = {"github": "wesnoth/wesnoth", "tags": r"^(1\.20\.[0-9]+)$"}
        checks, names = self.merge(
            {"communityChecks": True, "updateChecks": {"wesnoth-devel": mine}}
        )
        self.assertEqual(checks["wesnoth-devel"], mine)
        self.assertEqual(names, {"google-chrome"})

    def test_the_shipped_file_is_found(self):
        self.assertTrue(os.path.exists(community.path()))


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
            community.publish(results, self.NOW)
        repo, token, title, new_body, comment = update.call_args.args
        self.assertEqual(update.call_args.kwargs["label"], community.ISSUE_LABEL)
        return new_body, comment

    def test_all_working(self):
        body, comment = self.publish({"a": ("1.0", None), "b": ("2.0", None)})
        self.assertIn("All 2 work", body)
        self.assertIsNone(comment)

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
            community.publish({}, self.NOW)

    def test_track_only_counts_rules_that_ran(self):
        previous = {"gone": {"since": "x", "reason": "y"}}
        broken, newly, recovered = community.track(
            {"a": ("1.0", None)}, previous, self.NOW
        )
        self.assertEqual((broken, newly, recovered), ({}, [], []))


class ChangedInAPullRequest(unittest.TestCase):
    def test_only_added_or_changed_rules(self):
        base = {"google-chrome": CHROME, "wesnoth-devel": WESNOTH}
        head = {
            "google-chrome": CHROME,
            "wesnoth-devel": {**WESNOTH, "tags": "^(1\\.20\\..+)$"},
            "new": CHROME,
        }
        with mock.patch.object(
            community, "rules", side_effect=lambda f=None: base if f else head
        ):
            self.assertEqual(community.changed("main.nix"), ["new", "wesnoth-devel"])


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
