import io
import unittest
import urllib.error
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import repology
from tests.helpers import http_error, nix, response


class Repology(unittest.TestCase):
    def setUp(self):
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch("time.sleep"),
            mock.patch.object(repology, "_working", None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unknown_project_answers_empty_list_not_404(self):
        with mock.patch("urllib.request.urlopen", return_value=response([])):
            self.assertEqual(repology.project_by_name("nope"), (None, None))

    def test_404_means_not_found(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            self.assertEqual(repology.project_for_attr("nope"), (None, None))

    def test_project_name_taken_from_redirect(self):
        resp = response(
            [nix("x", "1", "newest")],
            "https://repology.org/api/v1/project/python%3Arequests",
        )
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(
                repology.project_for_attr("python313Packages.requests")[0],
                "python:requests",
            )

    def test_retries_then_succeeds(self):
        with (
            mock.patch.object(config, "REPOLOGY_URLS", ["https://a"]),
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[http_error(502), http_error(502), response(["ok"])],
            ) as urlopen,
        ):
            self.assertEqual(repology.get("/x")[0], ["ok"])
            self.assertEqual(urlopen.call_count, 3)

    def test_gives_up_after_all_retries(self):
        with (
            mock.patch.object(config, "REPOLOGY_URLS", ["https://a", "https://b"]),
            mock.patch(
                "urllib.request.urlopen", side_effect=urllib.error.URLError("down")
            ) as urlopen,
        ):
            with self.assertRaises(urllib.error.URLError):
                repology.get("/x")
            self.assertEqual(urlopen.call_count, 2 * (1 + len(config.RETRY_DELAYS)))

    def test_domain_that_answered_is_tried_first_afterwards(self):
        urls = []

        def urlopen(req, timeout):
            urls.append(req.full_url)
            if req.full_url.startswith("https://a"):
                raise urllib.error.URLError("refused")
            return response(["ok"])

        with (
            mock.patch.object(config, "REPOLOGY_URLS", ["https://a", "https://b"]),
            mock.patch("urllib.request.urlopen", side_effect=urlopen),
        ):
            repology.get("/1")
            repology.get("/2")
            repology.get("/3")
        self.assertEqual(
            urls, ["https://a/1", "https://b/1", "https://b/2", "https://b/3"]
        )

    def test_falls_back_again_if_the_working_domain_fails(self):
        with (
            mock.patch.object(config, "REPOLOGY_URLS", ["https://a", "https://b"]),
            mock.patch.object(repology, "_working", "https://b"),
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[urllib.error.URLError("down"), response(["ok"])],
            ) as urlopen,
        ):
            self.assertEqual(repology.get("/x")[0], ["ok"])
        self.assertEqual(
            [c.args[0].full_url for c in urlopen.call_args_list],
            ["https://b/x", "https://a/x"],
        )


class Trimmed(unittest.TestCase):
    """data/ keeps only what nixkeeper reads of Repology's entries."""

    FULL = {
        "repo": "alpine_edge",
        "srcname": "xournalpp",
        "binname": "xournalpp",
        "visiblename": "xournalpp",
        "version": "1.2.8",
        "origversion": "1.2.8-r0",
        "status": "newest",
        "summary": "Handwriting notetaking software",
        "licenses": ["GPL-2.0-or-later"],
        "maintainers": ["someone@example.org"],
    }

    def test_only_the_fields_read(self):
        self.assertEqual(
            repology.trimmed([self.FULL, {**self.FULL, "vulnerable": True}]),
            [
                {
                    "repo": "alpine_edge",
                    "srcname": "xournalpp",
                    "version": "1.2.8",
                    "status": "newest",
                },
                {
                    "repo": "alpine_edge",
                    "srcname": "xournalpp",
                    "version": "1.2.8",
                    "status": "newest",
                    "vulnerable": True,
                },
            ],
        )

    def test_each_once_in_repologys_order(self):
        doc = {**self.FULL, "binname": "xournalpp-doc", "summary": "Docs"}
        arch = {**self.FULL, "repo": "arch"}
        trimmed = repology.trimmed([self.FULL, doc, arch, self.FULL])
        self.assertEqual([e["repo"] for e in trimmed], ["alpine_edge", "arch"])

    def test_lookups_return_them_trimmed(self):
        doc = {**self.FULL, "binname": "xournalpp-doc"}
        with mock.patch(
            "urllib.request.urlopen", return_value=response([self.FULL, doc])
        ):
            name, entries = repology.project_by_name("xournalpp")
        self.assertEqual(name, "xournalpp")
        self.assertEqual(entries, repology.trimmed([self.FULL]))
