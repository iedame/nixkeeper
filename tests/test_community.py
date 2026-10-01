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
