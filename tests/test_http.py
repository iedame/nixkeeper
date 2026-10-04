"""Slowing down when a server asks (Retry-After, GitHub's rate limits):
sources/http.py, and its use in Repology's and GitHub's requests."""

import gzip
import io
import unittest
import urllib.error
from datetime import UTC, datetime
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import github, http, repology
from tests.helpers import response


class Case(unittest.TestCase):
    def slow_down(self, code=429, **headers):
        """A "slow down" answer (429 by default) with headers, closed after
        the test (an HTTPError is also an open response)."""
        err = urllib.error.HTTPError(
            "https://example.org", code, "err", headers, io.BytesIO()
        )
        self.addCleanup(err.close)
        return err


class AskedWait(Case):
    NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)

    def test_seconds(self):
        self.assertEqual(http.asked_wait(self.slow_down(**{"Retry-After": "7"})), 7)

    def test_a_date(self):
        err = self.slow_down(503, **{"Retry-After": "Fri, 02 Oct 2026 12:01:30 GMT"})
        self.assertEqual(http.asked_wait(err, now=self.NOW), 90)

    def test_only_when_asked_to_slow_down(self):
        self.assertIsNone(http.asked_wait(self.slow_down(429)))
        self.assertIsNone(http.asked_wait(self.slow_down(500, **{"Retry-After": "7"})))
        self.assertIsNone(http.asked_wait(urllib.error.URLError("down")))
        self.assertIsNone(http.asked_wait(self.slow_down(**{"Retry-After": "soon"})))


class Retries(Case):
    def setUp(self):
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch.object(config, "RETRY_DELAYS", [5, 15]),
            mock.patch.object(repology, "_working", None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sleep = mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_waits_as_long_as_asked(self):
        answers = [self.slow_down(**{"Retry-After": "40"}), response("ok")]
        answers[1].read.return_value = b"ok"
        with mock.patch("urllib.request.urlopen", side_effect=answers):
            self.assertEqual(http.get("https://x/"), "ok")
        self.sleep.assert_called_once_with(40)

    def test_never_shorter_than_planned(self):
        answers = [self.slow_down(**{"Retry-After": "1"}), response("ok")]
        answers[1].read.return_value = b"ok"
        with mock.patch("urllib.request.urlopen", side_effect=answers):
            http.get("https://x/")
        self.sleep.assert_called_once_with(5)

    def test_gives_up_when_asked_to_wait_too_long(self):
        err = self.slow_down(**{"Retry-After": str(config.MAX_RETRY_AFTER + 1)})
        with (
            mock.patch("urllib.request.urlopen", side_effect=err) as urlopen,
            self.assertRaises(urllib.error.HTTPError),
        ):
            http.get("https://x/")
        self.assertEqual(urlopen.call_count, 1)  # no retry, no wait
        self.sleep.assert_not_called()

    def test_repology_too(self):
        answers = [self.slow_down(**{"Retry-After": "30"}), response(["ok"])]
        with (
            mock.patch.object(config, "REPOLOGY_URLS", ["https://a"]),
            mock.patch("urllib.request.urlopen", side_effect=answers),
        ):
            self.assertEqual(repology.get("/x")[0], ["ok"])
        self.sleep.assert_called_once_with(30)


class GitHubRateLimit(Case):
    def test_retry_after(self):
        self.assertEqual(
            github.rate_limit_wait(self.slow_down(403, **{"Retry-After": "60"})), 60
        )

    def test_until_the_reset(self):
        err = self.slow_down(
            403, **{"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1100"}
        )
        self.assertEqual(github.rate_limit_wait(err, now=1000), 100)

    def test_not_a_rate_limit(self):
        self.assertIsNone(github.rate_limit_wait(self.slow_down(403)))  # no permission
        self.assertIsNone(
            github.rate_limit_wait(self.slow_down(500, **{"Retry-After": "5"}))
        )

    def test_waits_and_tries_once_more(self):
        answers = [
            self.slow_down(429, **{"Retry-After": "20"}),
            response({"data": {"x": 1}}),
        ]
        with (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch("time.sleep") as sleep,
            mock.patch("urllib.request.urlopen", side_effect=answers),
        ):
            self.assertEqual(github.graphql("token", "query", {}), {"x": 1})
        sleep.assert_called_once_with(20)

    def test_gives_up_on_a_long_wait(self):
        err = self.slow_down(429, **{"Retry-After": str(config.MAX_RETRY_AFTER + 1)})
        with (
            mock.patch("time.sleep") as sleep,
            mock.patch("urllib.request.urlopen", side_effect=err),
            self.assertRaises(urllib.error.HTTPError),
        ):
            github.graphql("token", "query", {})
        sleep.assert_not_called()


class Compressed(unittest.TestCase):
    """compressed=True: a big page from a trusted source comes gzipped."""

    def fetch(self, body, encoding, **kwargs):
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = body
        resp.headers = {"Content-Encoding": encoding} if encoding else {}
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            text = http.get("https://example.org/", **kwargs)
        return text, urlopen.call_args.args[0].headers

    def test_asks_for_gzip_and_unpacks_it(self):
        text, headers = self.fetch(gzip.compress(b"index"), "gzip", compressed=True)
        self.assertEqual(text, "index")
        self.assertEqual(headers.get("Accept-encoding"), "gzip")

    def test_a_plain_answer_too(self):
        text, _ = self.fetch(b"index", None, compressed=True)
        self.assertEqual(text, "index")

    def test_not_asked_otherwise(self):
        _, headers = self.fetch(b"index", None)
        self.assertNotIn("Accept-encoding", headers)
