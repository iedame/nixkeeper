"""nixkeeper-prs' digest: nixpkgs' open PRs and issues and the PRs merged
since the channel's commit, as github_bulk's listings."""

import io
import json
import unittest
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import about, http, prs_digest

NOW = "2026-10-09T12:00:00+00:00"
FILES = {
    "prs.json": {
        "format": 1,
        "prs": [
            {"n": 1, "title": "wine: 10.15 -> 10.16", "draft": False, "base": "master"}
        ],
    },
    "issues.json": {"format": 1, "issues": [{"n": 7, "title": "wine: crashes"}]},
    "merged.json": {
        "format": 1,
        "prs": [{"n": 4, "title": "x: 1 -> 2", "draft": False, "base": "master"}],
    },
}


def meta(at="2026-10-09T10:00:00+00:00", revision="abc", merged_at=None):
    return {
        "format": 1,
        "generatedAt": at,
        "issues": {"count": 1, "at": at},
        "merged": {"count": 1, "at": merged_at or at, "revision": revision},
    }


class Load(unittest.TestCase):
    def load(self, info, revision="abc"):
        def get(url, compressed=False):
            name = url.rsplit("/", 1)[1]
            return json.dumps(info if name == "meta.json" else FILES[name])

        with (
            mock.patch.object(config, "PRS_DIGEST_URL", "https://d/"),
            mock.patch.object(http, "get", side_effect=get),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            return prs_digest.load(NOW, revision)

    def test_current(self):
        found = self.load(meta())
        prs, issues = found["open"]
        self.assertEqual(
            prs,
            [
                {
                    "number": 1,
                    "title": "wine: 10.15 -> 10.16",
                    "url": "https://github.com/NixOS/nixpkgs/pull/1",
                    "isDraft": False,
                    "baseRefName": "master",
                }
            ],
        )
        self.assertEqual(issues, [{"number": 7, "title": "wine: crashes"}])
        self.assertEqual([p["number"] for p in found["merged"]], [4])
        self.assertEqual(
            about.taken()["prs"],
            {
                "used": True,
                "at": "2026-10-09T10:00:00+00:00",
                "prs": 1,
                "issues": 1,
                "merged": 1,
            },
        )

    def test_merged_since_another_channel_commit_isnt_used(self):
        found = self.load(meta(), revision="newer")
        self.assertIsNotNone(found["open"])
        self.assertIsNone(found["merged"])
        self.assertEqual(
            about.taken()["prs"]["partly"], "merged PRs since another channel commit"
        )

    def test_too_old_or_off(self):
        found = self.load(meta(at="2026-10-09T01:00:00+00:00"))
        self.assertEqual(found, {"open": None, "merged": None})
        self.assertFalse(about.taken()["prs"]["used"])
        with mock.patch.object(config, "PRS_DIGEST_URL", ""):
            self.assertIsNone(prs_digest.load(NOW, "abc"))
        self.assertEqual(about.taken(), {})

    def test_unreadable(self):
        self.assertIsNone(self.load({"format": 2}))
        self.assertIn("couldn't be read", about.taken()["prs"]["why"])


if __name__ == "__main__":
    unittest.main()
