import gzip
import io
import json
import unittest
from unittest import mock

from nixkeeper import changes, config
from nixkeeper.sources import about, branches

NOW = "2026-10-08T06:00:00+00:00"
# Trimmed from nixkeeper-hydra's haskell-updates.json.gz (evaluation 1829685).
DIGEST = {
    "format": 1,
    "jobset": "nixpkgs/haskell-updates",
    "eval": 1829685,
    "fetchedAt": "2026-10-07T12:17:00+00:00",
    "columns": ["attr", "system", "build", "status", "name"],
    "jobs": [
        ["haskellPackages.Agda", "x86_64-linux", "347795412", "failed", "Agda-2.8.0.2"],
        [
            "haskellPackages.Cabal-hooks",
            "x86_64-linux",
            "347795500",
            "ok",
            "Cabal-hooks-3.18",
        ],
        [
            "haskellPackages.amazonka-lookoutequipment",
            "x86_64-linux",
            "347796162",
            "ok",
            "amazonka-lookoutequipment-2.0-unstable-2026-06-10",
        ],
        ["haskellPackages.other", "aarch64-linux", "1", "ok", "other-1.0"],
    ],
}


class Load(unittest.TestCase):
    def setUp(self):
        about.taken()
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            # The tests turn the digests off (tests/__init__.py): on, here.
            mock.patch.object(config, "HYDRA_DIGEST_URL", "https://example.org/data/"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def serve(self, body):
        data = None if body is None else gzip.compress(json.dumps(body).encode())
        return mock.patch.object(branches.http, "get_bytes", return_value=data)

    def test_its_jobs_and_versions(self):
        with self.serve(DIGEST):
            jobs = branches.load("haskell-updates", NOW)
        self.assertEqual(
            jobs["haskellPackages.Agda"],
            {"version": "2.8.0.2", "status": "failed", "build": "347795412"},
        )
        self.assertEqual(jobs["haskellPackages.Cabal-hooks"]["version"], "3.18")
        self.assertNotIn("haskellPackages.other", jobs)  # not x86_64-linux
        noted = about.taken()["branch:haskell-updates"]
        self.assertEqual(
            (noted["used"], noted["eval"], noted["jobs"]), (True, 1829685, 3)
        )

    def test_old_or_missing(self):
        with self.serve({**DIGEST, "fetchedAt": "2026-10-05T00:00:00+00:00"}):
            self.assertIsNone(branches.load("haskell-updates", NOW))
        self.assertEqual(about.taken()["branch:haskell-updates"]["why"], "too old")
        with self.serve(None):
            self.assertIsNone(branches.load("haskell-updates", NOW))

    def test_only_when_tracked(self):
        self.assertEqual(
            branches.wanted(["haskellPackages.Agda", "zlib"]), ["haskell-updates"]
        )
        self.assertEqual(branches.wanted(["zlib"]), [])


class Apply(unittest.TestCase):
    def test_rows_get_what_the_branch_has(self):
        rows = [
            {"name": "haskellPackages.Agda", "attrs": ["haskellPackages.Agda"]},
            {"name": "zlib", "attrs": ["zlib"]},
        ]
        jobs = {
            "haskellPackages.Agda": {
                "version": "2.8.0.2",
                "status": "failed",
                "build": "1",
            }
        }
        branches.apply(rows, "haskell-updates", jobs)
        self.assertEqual(
            rows[0]["branch"],
            {
                "name": "haskell-updates",
                "version": "2.8.0.2",
                "status": "failed",
                "build": "1",
            },
        )
        self.assertNotIn("branch", rows[1])


class OnBranch(unittest.TestCase):
    def row(self, version, **extra):
        return {
            "nixStatus": "outdated",
            "nixVersion": "3.16",
            "refVersion": "3.18",
            "branch": {"name": "haskell-updates", "version": version},
            **extra,
        }

    def test_waiting_for_the_branchs_merge(self):
        self.assertTrue(changes.on_branch(self.row("3.18")))
        self.assertTrue(changes.on_branch(self.row("3.19")))  # newer still
        self.assertFalse(changes.on_branch(self.row("3.17")))  # not there yet
        self.assertFalse(changes.on_branch(self.row("3.18", nixStatus="newest")))
        self.assertFalse(
            changes.on_branch({"nixStatus": "outdated", "refVersion": "1"})
        )


if __name__ == "__main__":
    unittest.main()
