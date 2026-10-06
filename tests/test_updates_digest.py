"""nixkeeper-updates' digest of nixpkgs-update, and the attempts taken from
it (nixpkgs_update.add_attempts)."""

import gzip
import io
import json
import unittest
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import about, http, nixpkgs_update, updates_digest
from tests.helpers import pkg

NOW = "2026-10-05T18:00:00+00:00"
LOG = "https://nixpkgs-update-logs.nixos.org"


def read(attr, outcome="failed", day="2026-10-05", parser=nixpkgs_update.PARSER):
    """An attempt as the digest reads it (with its start)."""
    return {
        "attr": attr,
        "date": day,
        "started": 1791210053,
        "log": f"{LOG}/{attr}/{day}.log",
        "parser": parser,
        "outcome": outcome,
    }


class Load(unittest.TestCase):
    def serve(self, meta, entries):
        body = gzip.compress(
            "".join(json.dumps(e) + "\n" for e in entries).encode(), mtime=0
        )
        return (
            mock.patch.object(config, "UPDATES_DIGEST_URL", "https://d/"),
            mock.patch.object(http, "get", return_value=json.dumps(meta)),
            mock.patch.object(http, "get_bytes", return_value=body),
            mock.patch("sys.stderr", io.StringIO()),
        )

    def test_current(self):
        meta = {"format": 1, "fetchedAt": "2026-10-05T15:00:00+00:00"}
        patches = self.serve(meta, [{"attr": "wesnoth", "attempt": read("wesnoth")}])
        with patches[0], patches[1], patches[2], patches[3]:
            found = updates_digest.load(NOW)
        self.assertEqual(found, {"wesnoth": {"attempt": read("wesnoth")}})
        # Noted for the page: when it's from, and how many it hasn't read.
        self.assertEqual(
            about.taken()["updates"],
            {"used": True, "at": "2026-10-05T15:00:00+00:00", "pending": 0},
        )

    def test_old_or_off_isnt_used(self):
        meta = {"format": 1, "fetchedAt": "2026-10-04T15:00:00+00:00"}
        patches = self.serve(meta, [])
        with patches[0], patches[1], patches[2], patches[3]:
            self.assertIsNone(updates_digest.load(NOW))
        self.assertEqual(
            about.taken()["updates"],
            {"used": False, "why": "too old", "at": "2026-10-04T15:00:00+00:00"},
        )
        with mock.patch.object(config, "UPDATES_DIGEST_URL", ""):
            self.assertIsNone(updates_digest.load(NOW))
        self.assertEqual(about.taken(), {})  # turned off: nothing to say

    def test_attempt_only_when_read_with_these_rules(self):
        entry = {"attempt": read("python3Packages.foo")}
        attempt = updates_digest.attempt(
            entry, "python313Packages.foo", nixpkgs_update.PARSER
        )
        self.assertEqual(attempt["attr"], "python313Packages.foo")  # nixkeeper's
        self.assertNotIn("started", attempt)
        self.assertIsNone(updates_digest.attempt({**entry, "pending": "x"}, "a", 2))
        self.assertIsNone(updates_digest.attempt(entry, "a", nixpkgs_update.PARSER + 1))


class AddAttempts(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)

    def add(self, rows, digest, bulk=frozenset(), read=None):
        nixpkgs = {a: pkg(a) for row in rows for a in row["attrs"]}
        with (
            mock.patch.object(nixpkgs_update, "directory_dates", return_value=None),
            mock.patch.object(
                nixpkgs_update, "latest_attempt", side_effect=read or AssertionError
            ) as latest,
        ):
            nixpkgs_update.add_attempts(
                rows, nixpkgs, {"packages": []}, NOW, bulk=bulk, digest=digest
            )
        return latest

    def test_from_the_digest_without_reading_a_log(self):
        rows = [{"name": "wesnoth", "attrs": ["wesnoth"], "nixVersion": "1.18.7"}]
        self.add(rows, {"wesnoth": {"attempt": read("wesnoth")}})
        self.assertEqual(rows[0]["update"]["outcome"], "failed")
        self.assertTrue(rows[0]["updateFailure"])

    def test_never_tried(self):
        rows = [{"name": "new", "attrs": ["new"], "nixVersion": "1"}]
        self.add(rows, {})
        self.assertIsNone(rows[0]["update"])

    def test_a_lists_package_pending_there_is_read(self):
        rows = [{"name": "unciv", "attrs": ["unciv"], "nixVersion": "1"}]
        digest = {"unciv": {"attempt": read("unciv", "noChange"), "pending": "x"}}
        fresh = {**read("unciv", "prOpened"), "pr": 1}
        fresh.pop("started")
        latest = self.add(rows, digest, read=lambda *a: dict(fresh))
        latest.assert_called_once()
        self.assertEqual(rows[0]["update"]["outcome"], "prOpened")

    def test_in_bulk_the_last_read_or_unread(self):
        rows = [
            {"name": "behind", "attrs": ["behind"], "nixVersion": "1"},
            {"name": "never", "attrs": ["never"], "nixVersion": "1"},
        ]
        digest = {
            "behind": {"attempt": read("behind", "noChange"), "pending": "x"},
            "never": {"pending": "x"},
        }
        self.add(rows, digest, bulk={"behind", "never"})
        self.assertEqual(rows[0]["update"]["outcome"], "noChange")
        self.assertNotIn("unread", rows[0])
        self.assertIsNone(rows[1]["update"])
        self.assertEqual(rows[1]["unread"], ["update"])
