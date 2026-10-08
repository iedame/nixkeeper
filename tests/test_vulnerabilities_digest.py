import gzip
import io
import json
import unittest
from unittest import mock

from nixkeeper import config
from nixkeeper.changes import is_vulnerable
from nixkeeper.sources import about, http
from nixkeeper.sources import vulnerabilities_digest as vd

NOW = "2026-10-08T15:00:00+00:00"


def suggestion(cve, attr, status, ranges, issue="NIXPKGS-2026-1", **more):
    return {
        "cve": cve,
        "issue": issue,
        "title": f"{cve}'s title",
        "affected": [{"product": "x", "versions": ranges}],
        "packages": {
            attr: {
                "version": "1.0",
                "status": status,
                "branch": "master",
                "branches": {
                    "master": {"version": "1.0", "status": status},
                    "release-26.05": {"version": "0.9", "status": "affected"},
                },
            }
        },
        **more,
    }


# The digest as nixkeeper-vulnerabilities publishes it (its tracker part
# keyed as there: suggestions by id, packages by attribute).
SUGGESTIONS = {
    "1": suggestion(
        "CVE-2026-1",
        "aspell",
        "affected",
        [["affected", "<2.0"]],
        severity="high",
        score=7.5,
    ),
    "2": suggestion("CVE-2026-2", "aspell", "unknown", [["affected", "==< 1.5"]]),
    "3": suggestion("CVE-2026-3", "aspell", "unknown", [["affected", "<0.5"]]),
    "4": suggestion("CVE-2026-4", "aspell", "unknown", [["affected", "1.0, 1.1"]]),
    "5": suggestion("CVE-2026-5", "aspell", "affected", [], issue="NIXPKGS-2026-5"),
}
DIGEST = {
    "tracker": {
        "suggestions": SUGGESTIONS,
        "issues": {
            "NIXPKGS-2026-1": {
                "status": "affected",
                "github": "https://github.com/NixOS/nixpkgs/issues/1",
            },
            "NIXPKGS-2026-5": {"status": "notForUs"},
        },
        "packages": {
            "aspell": [
                {"suggestion": k, "status": s["packages"]["aspell"]["status"]}
                for k, s in SUGGESTIONS.items()
            ]
        },
    },
    "osv": {
        "advisories": {
            "GHSA-a": {
                "cves": ["CVE-2026-1"],
                "summary": "same CVE",
                "ecosystem": "PyPI",
            },
            "GHSA-b": {
                "cves": ["CVE-2026-9"],
                "summary": "another",
                "severity": "moderate",
                "ecosystem": "PyPI",
            },
        },
        "packages": {"aspell": ["GHSA-a", "GHSA-b"]},
    },
}


class Ranges(unittest.TestCase):
    def test_the_shapes_the_tracker_gives(self):
        cases = [
            ("1.2", "<1.3", True),
            ("1.3", "<1.3", False),
            ("1.0.45", "==< 1.0.45", False),
            ("1.0.44", "==< 1.0.45", True),
            ("1.38.1", "==>= 1.38.0, < 1.38.3", True),
            ("1.38.3", "==>= 1.38.0, < 1.38.3", False),
            ("1.011", "=<1.011", True),
            ("0.10", "==0.10", True),
            ("0.10.1", "==0.10", False),
            ("0.24.6", "=== 0.24.6", True),
            ("2026.4.1", "==<= 2026.4.1", True),
            ("1.17", "<v1.18.0", True),
            ("2.540", "<2.541.*", True),
            ("9", "*", True),
        ]
        for version, expression, expected in cases:
            with self.subTest(version=version, expression=expression):
                self.assertIs(vd.matches(version, expression), expected)

    def test_what_cant_be_read(self):
        for expression in ("<x.59.21", "<1.46.0, 1.45.4, 1.44.6", "", "later"):
            with self.subTest(expression=expression):
                self.assertIsNone(vd.matches("1.0", expression))

    def test_affected_unaffected_or_unknown(self):
        ranges = [{"versions": [["affected", "<1.2"], ["unaffected", ">=1.2"]]}]
        self.assertEqual(vd.by_version("1.1", ranges), "affected")
        self.assertEqual(vd.by_version("1.2", ranges), "fixed")
        self.assertIsNone(vd.by_version("1.0", [{"versions": [["affected", "x.1"]]}]))
        self.assertIsNone(vd.by_version("1.0", []))  # no ranges: can't tell
        self.assertIsNone(vd.by_version(None, ranges))


class Verdicts(unittest.TestCase):
    def found(self, **row):
        return {v["id"]: v for v in vd.for_row({"name": "aspell", **row}, DIGEST)}

    def test_each_verdict(self):
        found = self.found(nixVersion="1.0")
        self.assertEqual(found["CVE-2026-1"]["verdict"], "affected")
        self.assertEqual(found["CVE-2026-2"]["verdict"], "byVersion")  # 1.0 < 1.5
        self.assertEqual(found["CVE-2026-3"]["verdict"], "fixed")  # not < 0.5
        self.assertEqual(found["CVE-2026-4"]["verdict"], "unconfirmed")
        self.assertEqual(found["CVE-2026-5"]["verdict"], "dismissed")  # not for us
        # OSV: not for a CVE the tracker has; another one, counted.
        self.assertNotIn("GHSA-a", found)
        self.assertEqual(found["GHSA-b"]["verdict"], "osv")

    def test_what_an_entry_says(self):
        cve = self.found(nixVersion="1.0")["CVE-2026-1"]
        self.assertEqual((cve["severity"], cve["score"]), ("high", 7.5))
        self.assertEqual(cve["issue"], "NIXPKGS-2026-1")
        self.assertEqual(cve["github"], "https://github.com/NixOS/nixpkgs/issues/1")
        self.assertEqual(cve["releases"], {"release-26.05": "affected"})

    def test_counted_first_worst_first(self):
        ids = [
            v["id"] for v in vd.for_row({"name": "aspell", "nixVersion": "1.0"}, DIGEST)
        ]
        self.assertEqual(ids[0], "CVE-2026-1")  # high, counted
        self.assertLess(ids.index("GHSA-b"), ids.index("CVE-2026-3"))  # counted first

    def test_by_any_attribute(self):
        found = vd.for_row(
            {"name": "aspell-full", "attrs": ["aspell"], "nixVersion": "1.0"}, DIGEST
        )
        self.assertTrue(found)
        self.assertEqual(vd.for_row({"name": "other", "nixVersion": "1.0"}, DIGEST), [])


class Vulnerable(unittest.TestCase):
    def test_any_source(self):
        rows = [{"name": "aspell", "nixVersion": "1.0"}, {"name": "other"}]
        self.assertEqual(vd.add(rows, DIGEST), 1)
        self.assertTrue(is_vulnerable(rows[0]))
        self.assertNotIn("vulnerabilities", rows[1])
        self.assertFalse(is_vulnerable(rows[1]))
        self.assertEqual(
            vd.summary(rows[0]), {"n": 3, "severity": "high", "by": ["osv", "tracker"]}
        )

    def test_repology_still_counts(self):
        # The tracker's entries all fixed: Repology's flag still counts (its
        # CVEs may be others the tracker has no entry for).
        row = {"name": "aspell", "nixVersion": "9.0", "nixVulnerable": True}
        row["vulnerabilities"] = [
            {"id": "CVE-2026-3", "source": "tracker", "verdict": "fixed"}
        ]
        self.assertTrue(is_vulnerable(row))
        self.assertEqual(vd.summary(row), {"n": 0, "by": ["repology"]})
        del row["nixVulnerable"]
        self.assertFalse(is_vulnerable(row))
        self.assertIsNone(vd.summary(row))

    def test_without_a_digest_nothing_changes(self):
        rows = [{"name": "aspell", "nixVulnerable": True}]
        self.assertEqual(vd.add(rows, None), 0)
        self.assertNotIn("vulnerabilities", rows[0])
        self.assertTrue(is_vulnerable(rows[0]))


class Load(unittest.TestCase):
    def load(self, meta):
        def get(url, *args, **kwargs):
            self.assertTrue(url.endswith("meta.json"))
            return json.dumps(meta)

        body = gzip.compress(json.dumps({"format": 1, **DIGEST}).encode())
        with (
            mock.patch.object(config, "VULNERABILITIES_DIGEST_URL", "https://digest/"),
            mock.patch.object(http, "get", side_effect=get),
            mock.patch.object(http, "get_bytes", return_value=body),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            about.taken()
            return vd.load(NOW), about.taken()

    def test_used_when_complete_and_recent(self):
        meta = {
            "format": 1,
            "tracker": {
                "complete": True,
                "readAt": "2026-10-08T14:00:00+00:00",
                "suggestions": 5,
                "packages": 1,
            },
            "osv": {"readAt": NOW, "advisories": 2, "packages": 1},
        }
        digest, noted = self.load(meta)
        self.assertIn("aspell", digest["tracker"]["packages"])
        self.assertTrue(noted["tracker"]["used"])
        self.assertTrue(noted["osv"]["used"])

    def test_not_until_read_through_nor_when_old(self):
        for tracker in (
            {"complete": False, "readAt": NOW},
            {"complete": True, "readAt": "2026-10-01T00:00:00+00:00"},
        ):
            with self.subTest(tracker=tracker):
                digest, noted = self.load({"format": 1, "tracker": tracker})
                self.assertIsNone(digest)
                self.assertFalse(noted["tracker"]["used"])


if __name__ == "__main__":
    unittest.main()
