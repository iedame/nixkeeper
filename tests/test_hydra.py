import io
import unittest
import urllib.error
from unittest import mock

from nixkeeper import config
from nixkeeper.sources import hydra
from tests.helpers import http_error, pkg, response

NOW = "2026-09-30T06:00:00+00:00"

# Shaped like hydra.nixos.org's answers (checked 2026-09-28).
OK = [{"id": 345280810, "buildstatus": 0, "finished": 1, "system": "aarch64-darwin"}]
FAILED = [
    {"id": 345227373, "buildstatus": 1, "finished": 1, "system": "aarch64-darwin"}
]
LAST_SUCCESS = {"id": 1, "buildstatus": 0, "stoptime": 1710403200}  # 2024-03-14


def fake_hydra(latest, last_success=None):
    """urlopen answering latestbuilds from latest[job] (missing: []) and
    /latest from last_success[job] (missing: 404)."""
    last_success = last_success or {}
    calls = []

    def urlopen(req, timeout):
        url = req.full_url
        calls.append(url)
        if "/api/latestbuilds?" in url:
            job = url.split("job=")[1]
            return response(latest.get(job, []))
        job = url.split("/")[-2]
        if job in last_success:
            return response(last_success[job])
        raise http_error(404)

    return urlopen, calls


class Hydra(unittest.TestCase):
    def setUp(self):
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch("time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def check(self, latest, last_success=None):
        urlopen, calls = fake_hydra(latest, last_success)
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            return hydra.check("ac-library", "aarch64-darwin"), calls

    def test_ok(self):
        result, calls = self.check({"ac-library.aarch64-darwin": OK})
        self.assertEqual(
            result,
            {
                "attr": "ac-library",
                "system": "aarch64-darwin",
                "status": "ok",
                "build": 345280810,
            },
        )
        self.assertEqual(len(calls), 1)  # no last-success lookup needed

    def test_failed_gets_last_success(self):
        result, _ = self.check(
            {"ac-library.aarch64-darwin": FAILED},
            {"ac-library.aarch64-darwin": LAST_SUCCESS},
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["build"], 345227373)
        self.assertEqual(result["lastSuccess"], "2024-03-14T08:00:00+00:00")

    def test_failed_never_succeeded(self):
        result, _ = self.check({"ac-library.aarch64-darwin": FAILED})
        self.assertIsNone(result["lastSuccess"])

    def test_not_on_hydra(self):
        result, _ = self.check({})
        self.assertEqual(result["status"], "notBuilt")

    def test_marked_broken(self):
        urlopen, _ = fake_hydra(
            {"ac-library.aarch64-darwin": FAILED},
            {"ac-library.aarch64-darwin": LAST_SUCCESS},
        )
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            result = hydra.check("ac-library", "aarch64-darwin", broken=True)
            never_built = hydra.check("other", "aarch64-darwin", broken=True)
        self.assertEqual(result["status"], "broken")
        self.assertEqual(result["build"], 345227373)
        self.assertEqual(result["lastSuccess"], "2024-03-14T08:00:00+00:00")
        self.assertEqual(
            never_built,
            {"attr": "other", "system": "aarch64-darwin", "status": "broken"},
        )

    def test_statuses(self):
        self.assertEqual(hydra.status(0), "ok")
        self.assertEqual(hydra.status(1), "failed")
        self.assertEqual(hydra.status(6), "failed")
        self.assertEqual(hydra.status(2), "dependency")
        self.assertEqual(hydra.status(7), "unfinished")

    def test_systems(self):
        self.assertEqual(hydra.systems(pkg("x")), config.HYDRA_SYSTEMS)
        self.assertEqual(
            hydra.systems(
                pkg("x", ["x86_64-linux", "x86_64-darwin", "aarch64-darwin"])
            ),
            ["x86_64-linux", "aarch64-darwin"],
        )
        no_hydra = pkg("x", ["x86_64-linux"])
        no_hydra["meta"]["hydraPlatforms"] = []
        self.assertEqual(hydra.systems(no_hydra), [])

    def test_unfree(self):
        unfree = pkg("x")
        unfree["meta"]["license"] = {"free": False, "shortName": "unfree"}
        mixed = pkg("x")
        mixed["meta"]["license"] = [{"free": True}, {"free": False}]
        free = pkg("x")
        free["meta"]["license"] = {"free": True}
        self.assertTrue(hydra.is_unfree(unfree))
        self.assertTrue(hydra.is_unfree(mixed))
        self.assertFalse(hydra.is_unfree(free))
        self.assertFalse(hydra.is_unfree(pkg("x")))  # no license info


class AddBuilds(unittest.TestCase):
    def setUp(self):
        self.stderr = io.StringIO()
        for patcher in (
            mock.patch("sys.stderr", self.stderr),
            mock.patch("time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_rows(self):
        edge = pkg("microsoft-edge", ["x86_64-linux"])
        edge["meta"]["license"] = {"free": False}
        nixpkgs = {
            "ac-library": pkg("ac-library", ["x86_64-linux", "aarch64-darwin"]),
            "microsoft-edge": edge,
        }
        rows = [
            {"name": "ac-library", "attrs": ["ac-library"]},
            {"name": "microsoft-edge", "attrs": ["microsoft-edge"]},
            {"name": "gone", "attrs": []},
        ]
        urlopen, calls = fake_hydra(
            {
                "ac-library.x86_64-linux": OK,
                "ac-library.aarch64-darwin": FAILED,
            }
        )
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            hydra.add_builds(rows, nixpkgs, {"packages": []}, NOW)
        self.assertEqual(
            [(b["system"], b["status"]) for b in rows[0]["builds"]],
            [("x86_64-linux", "ok"), ("aarch64-darwin", "failed")],
        )
        # Marked broken on darwin: the same failure, but known.
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            hydra.add_builds(
                rows,
                nixpkgs,
                {"packages": []},
                NOW,
                {"ac-library": ["aarch64-darwin"]},
            )
        self.assertEqual(
            [(b["system"], b["status"]) for b in rows[0]["builds"]],
            [("x86_64-linux", "ok"), ("aarch64-darwin", "broken")],
        )
        self.assertEqual(rows[1], {**rows[1], "unfree": True, "builds": []})
        self.assertNotIn("builds", rows[2])  # not in nixpkgs
        self.assertFalse(any("microsoft-edge" in url for url in calls))

    def test_hydra_down_reuses_previous_and_stops_asking(self):
        nixpkgs = {f"p{i}": pkg(f"p{i}", ["x86_64-linux"]) for i in range(6)}
        rows = [{"name": name, "attrs": [name]} for name in nixpkgs]
        old = {"attr": "p0", "system": "x86_64-linux", "status": "failed", "build": 9}
        previous = {"packages": [{"name": "p0", "builds": [old]}]}
        with (
            mock.patch.object(config, "RETRY_DELAYS", []),
            mock.patch(
                "urllib.request.urlopen", side_effect=urllib.error.URLError("down")
            ) as urlopen,
        ):
            hydra.add_builds(rows, nixpkgs, previous, NOW)
        self.assertEqual(rows[0]["builds"], [old])
        self.assertEqual(rows[5]["builds"][0]["status"], "unknown")
        self.assertEqual(urlopen.call_count, config.HYDRA_MAX_CONSECUTIVE_FAILURES)
        self.assertIn("::warning::6 Hydra lookups failed", self.stderr.getvalue())
        # Every row says it's showing old results, and why.
        for r in rows:
            self.assertEqual(r["notRefreshed"]["builds"]["since"], NOW)
        self.assertIn("down", rows[0]["notRefreshed"]["builds"]["reason"])
        self.assertIn("didn't answer", rows[5]["notRefreshed"]["builds"]["reason"])

    def test_refreshed_rows_have_no_marker(self):
        nixpkgs = {"hello": pkg("hello", ["x86_64-linux"])}
        rows = [{"name": "hello", "attrs": ["hello"]}]
        urlopen, _ = fake_hydra({"hello.x86_64-linux": OK})
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            hydra.add_builds(rows, nixpkgs, {"packages": []}, NOW)
        self.assertNotIn("notRefreshed", rows[0])


class MasterVersion(unittest.TestCase):
    """What master has, from Hydra's build names, when it's ahead of the
    channel (a merged update the channel hasn't picked up yet)."""

    def row(self, *names, attrs=("wesnoth-devel",)):
        return {
            "name": attrs[0],
            "attrs": list(attrs),
            "builds": [
                {"attr": attr, "system": "x86_64-linux", "status": "ok", "name": name}
                for attr, name in names
            ],
        }

    def pkgs(self, version="1.19.24"):
        return {"wesnoth-devel": pkg("wesnoth-devel", version=version)}

    def test_master_ahead(self):
        row = self.row(("wesnoth-devel", "wesnoth-devel-1.19.28"))
        self.assertEqual(hydra.master_version(row, self.pkgs()), "1.19.28")

    def test_master_same_as_channel(self):
        row = self.row(("wesnoth-devel", "wesnoth-devel-1.19.24"))
        self.assertIsNone(hydra.master_version(row, self.pkgs()))

    def test_newest_across_platforms(self):
        row = self.row(
            ("wesnoth-devel", "wesnoth-devel-1.19.26"),
            ("wesnoth-devel", "wesnoth-devel-1.19.28"),
        )
        self.assertEqual(hydra.master_version(row, self.pkgs()), "1.19.28")

    def test_pname_with_dashes_and_other_names(self):
        # The pname, not the attribute, prefixes the name (1password-8.12.36).
        pkgs = {"_1password-gui": pkg("1password", version="8.12.34")}
        row = self.row(
            ("_1password-gui", "1password-8.12.36"), attrs=("_1password-gui",)
        )
        self.assertEqual(hydra.master_version(row, pkgs), "8.12.36")
        # A build whose name doesn't fit (renamed pname): no guess.
        row = self.row(("_1password-gui", "onepassword-9"), attrs=("_1password-gui",))
        self.assertIsNone(hydra.master_version(row, pkgs))

    def test_the_rows_own_attribute_first(self):
        pkgs = {
            "heroic": pkg("heroic", version="2.1"),
            "heroic-unwrapped": pkg("heroic-unwrapped", version="2.1"),
        }
        row = self.row(
            ("heroic-unwrapped", "heroic-unwrapped-2.3"),
            ("heroic", "heroic-2.2"),
            attrs=("heroic", "heroic-unwrapped"),
        )
        self.assertEqual(hydra.master_version(row, pkgs), "2.2")

    def test_add_builds_records_it(self):
        nixpkgs = {"hello": pkg("hello", ["x86_64-linux"], version="2.12.2")}
        rows = [{"name": "hello", "attrs": ["hello"]}]
        build = [{"id": 1, "buildstatus": 0, "nixname": "hello-2.12.3"}]
        urlopen, _ = fake_hydra({"hello.x86_64-linux": build})
        with (
            mock.patch("urllib.request.urlopen", side_effect=urlopen),
            mock.patch("time.sleep"),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            hydra.add_builds(rows, nixpkgs, {"packages": []}, NOW)
        self.assertEqual(rows[0]["builds"][0]["name"], "hello-2.12.3")
        self.assertEqual(rows[0]["master"], "2.12.3")
