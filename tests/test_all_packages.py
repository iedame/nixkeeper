"""With every package tracked (config.all_packages): the lists' packages read
as always, the rest of nixpkgs in bulk only."""

import io
import json
import os
import tempfile
import unittest
from unittest import mock

from nixkeeper import config, datastore, tracking
from nixkeeper.lookup import collect_projects
from nixkeeper.rows import build_rows
from nixkeeper.sources import hydra_digest, nixpkgs_update
from tests.helpers import nix, other, pkg

NOW = "2026-10-05T06:00:00+00:00"


class Setting(unittest.TestCase):
    def test_off_unless_turned_on(self):
        for value, on in (("", False), ("0", False), ("1", True), ("true", True)):
            with (
                mock.patch.object(config, "ALL_PACKAGES", None),
                mock.patch.dict(os.environ, {"NIXKEEPER_ALL_PACKAGES": value}),
            ):
                self.assertEqual(config.all_packages(), on, value)

    def test_the_command_wins(self):
        with (
            mock.patch.object(config, "ALL_PACKAGES", True),
            mock.patch.dict(os.environ, {"NIXKEEPER_ALL_PACKAGES": ""}),
        ):
            self.assertTrue(config.all_packages())


class Tracking(unittest.TestCase):
    def test_every_package_the_lists_dont_cover(self):
        nixpkgs = {
            "heroic": pkg("heroic"),
            "heroic-unwrapped": pkg("heroic"),
            "zlib": pkg("zlib"),
            "haskellPackages.zlib": pkg("zlib"),
        }
        listed = {"heroic": (["heroic", "heroic-unwrapped"], "heroic")}
        self.assertEqual(
            tracking.every_package(nixpkgs, listed),
            {
                "zlib": (["zlib"], "zlib"),
                "haskellPackages.zlib": (["haskellPackages.zlib"], "zlib"),
            },
        )

    def test_generated_sets_are_pending_unless_listed(self):
        rows = [
            {"name": "haskellPackages.a", "attrs": ["haskellPackages.a"], "lists": []},
            {
                "name": "haskellPackages.b",
                "attrs": ["haskellPackages.b"],
                "lists": ["x"],
            },
            {
                "name": "python3Packages.c",
                "attrs": ["python313Packages.c"],
                "lists": [],
            },
            {"name": "d", "attrs": ["d"], "lists": []},
        ]
        tracking.add_pending(rows)
        self.assertEqual(
            [(r.get("pending"), r.get("set")) for r in rows],
            [(True, "haskellPackages"), (None, None), (None, None), (None, None)],
        )


class Repology(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def collect(self, wanted, digest, previous=None):
        def resolve(*args, **kwargs):
            raise AssertionError("bulk packages are never looked up")

        return collect_projects(
            wanted,
            previous or {"packages": []},
            resolve=resolve,
            out_dir=self.dir.name,
            nixpkgs={"a": {"version": "2"}, "b": {"version": "1"}},
            now=NOW,
            digest=digest,
            bulk=set(wanted),
        )

    def test_from_the_digest_even_behind_the_channel(self):
        entries = [nix("a", "1", "outdated"), other("arch", "2", "newest")]
        projects = self.collect(
            {"a": (["a"], "a")}, {"a": ("a", entries, "2026-10-04")}
        )
        self.assertEqual(projects["a"]["entries"], entries)
        self.assertEqual(projects["a"]["checkedAt"], "2026-10-04T00:00:00+00:00")

    def test_not_on_repology(self):
        nixpkgs = {"b": {"version": "1", "pname": "b", "meta": {}}}
        projects = self.collect({"b": (["b"], "b")}, {})
        self.assertTrue(projects["unlisted:b"]["unlisted"])
        (row,) = build_rows(projects, nixpkgs)
        self.assertEqual((row["nixVersion"], row["nixStatus"]), ("1", "unlisted"))

    def test_never_joined_to_a_project_of_the_same_name(self):
        entries = [nix("python313Packages.c", "2", "newest")]
        projects = self.collect(
            {"python313Packages.c": (["python313Packages.c"], "c"), "c": (["c"], "c")},
            {"python313Packages.c": ("c", entries, "2026-10-04")},
        )
        self.assertEqual(projects["c"]["attrs"], ["python313Packages.c"])
        self.assertEqual(projects["unlisted:c"]["attrs"], ["c"])


def digest_row(attr, system, status, build="7", last=""):
    return {
        "attr": attr,
        "system": system,
        "status": status,
        "build": build,
        "finished": "2026-10-04T00:00:00Z",
        "name": f"{attr}-1",
        "lastSuccessBuild": last,
        "lastSuccessAt": "",
        "lastSuccessName": "",
    }


class Hydra(unittest.TestCase):
    JOBS = [
        ("ok", "x86_64-linux"),
        ("failing", "x86_64-linux"),
        ("queued", "x86_64-linux"),
        ("new", "x86_64-linux"),
        ("gone", "x86_64-linux"),
    ]

    def test_bulk_answers_never_ask(self):
        digest = {
            ("ok", "x86_64-linux"): digest_row("ok", "x86_64-linux", "ok"),
            ("failing", "x86_64-linux"): digest_row(
                "failing", "x86_64-linux", "failed"
            ),
            ("queued", "x86_64-linux"): digest_row("queued", "x86_64-linux", "queued"),
            ("new", "x86_64-linux"): digest_row("new", "x86_64-linux", "queued"),
        }
        before = {
            ("queued", "x86_64-linux"): {
                "attr": "queued",
                "system": "x86_64-linux",
                "status": "ok",
                "build": 5,
                "checkedAt": NOW,
            }
        }
        found = hydra_digest.bulk_answers(
            digest, self.JOBS, {"gone": ["x86_64-linux"]}, before
        )
        status = {attr: r["status"] for (attr, _), r in found.items()}
        self.assertEqual(
            status,
            {
                "ok": "ok",
                "failing": "failed",  # without its last success: the digest can't say
                "queued": "ok",  # the last sync's
                "new": "unknown",
                "gone": "broken",  # not in the evaluation, marked broken
            },
        )
        self.assertNotIn("lastSuccess", found["failing", "x86_64-linux"])
        self.assertNotIn("checkedAt", found["queued", "x86_64-linux"])

    def test_without_a_digest_as_the_last_sync_had_them(self):
        before = {
            ("ok", "x86_64-linux"): {
                "attr": "ok",
                "system": "x86_64-linux",
                "status": "ok",
            }
        }
        found = hydra_digest.bulk_answers(None, self.JOBS[:2], {}, before)
        self.assertEqual(found["ok", "x86_64-linux"]["status"], "ok")
        self.assertEqual(found["failing", "x86_64-linux"]["status"], "unknown")


class UpdateLogs(unittest.TestCase):
    def test_turns_outdated_and_failing_first_within_the_budget(self):
        nixpkgs = {n: pkg(n) for n in ("quiet", "outdated", "failing", "pending")}
        rows = [
            {"name": "quiet", "attrs": ["quiet"], "nixStatus": "newest"},
            {"name": "outdated", "attrs": ["outdated"], "nixStatus": "outdated"},
            {"name": "failing", "attrs": ["failing"], "nixStatus": "newest"},
            {"name": "pending", "attrs": ["pending"], "pending": True},
        ]
        before = {"failing": {"name": "failing", "updateFailure": True, "update": {}}}
        dates = {n: nixpkgs_update.datetime.now(nixpkgs_update.UTC) for n in nixpkgs}
        with mock.patch.object(config, "UPDATE_LOGS_BUDGET", 2):
            turns = nixpkgs_update.bulk_turns(
                rows, nixpkgs, before, dates, NOW, {r["name"] for r in rows}
            )
        self.assertEqual(turns, {"outdated", "failing"})

    def test_unread_last_time_still_waits_its_turn(self):
        nixpkgs = {"a": pkg("a")}
        rows = [{"name": "a", "attrs": ["a"], "nixStatus": "newest"}]
        long_ago = nixpkgs_update.datetime(2026, 1, 1, tzinfo=nixpkgs_update.UTC)
        unread = {"a": {"name": "a", "update": None, "unread": ["update"]}}
        read = {"a": {"name": "a", "update": None}}
        for before, turns in ((unread, {"a"}), (read, set())):
            with mock.patch.object(config, "UPDATE_LOGS_BUDGET", 1):
                self.assertEqual(
                    nixpkgs_update.bulk_turns(
                        rows, nixpkgs, before, {"a": long_ago}, NOW, {"a"}
                    ),
                    turns,
                )

    def test_none_read_beyond_the_lists_for_now(self):
        nixpkgs = {"a": pkg("a")}
        rows = [{"name": "a", "attrs": ["a"], "nixStatus": "outdated"}]
        dates = {"a": nixpkgs_update.datetime.now(nixpkgs_update.UTC)}
        self.assertEqual(
            nixpkgs_update.bulk_turns(rows, nixpkgs, {}, dates, NOW, {"a"}), set()
        )

    def test_no_turns_without_the_sites_index(self):
        rows = [{"name": "a", "attrs": ["a"]}]
        self.assertEqual(
            nixpkgs_update.bulk_turns(rows, {"a": pkg("a")}, {}, None, NOW, {"a"}),
            set(),
        )


def row(name, **extra):
    return {
        "name": name,
        "attrs": [name],
        "nixStatus": "newest",
        "nixVersion": "1",
        **extra,
    }


class Data(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = os.path.join(self.dir.name, "data")

    def read(self, name):
        with open(os.path.join(self.out, name)) as f:
            return json.load(f)

    def test_status_letters(self):
        self.assertEqual(datastore.status(row("a")), "u")
        self.assertEqual(datastore.status(row("a", nixStatus="outdated")), "o")
        self.assertEqual(datastore.status(row("a", updateFailure=True)), "f")
        self.assertEqual(datastore.status(row("a", nixStatus="unlisted")), "n")
        self.assertEqual(datastore.status(row("a", nixVulnerable=True)), "uv")
        waiting = row("a", nixStatus="outdated", refVersion="2", master="2")
        self.assertEqual(datastore.status(waiting), "m")

    def test_slug(self):
        self.assertEqual(datastore.slug("Security review"), "security-review")
        self.assertEqual(datastore.slug("Qt-KDE"), "qt-kde")

    def test_views_names_and_counts(self):
        rows = [
            row(
                "a",
                maintainers=["Iedame"],
                lists=["gaming-team"],
                teams=["Gaming"],
                dataFile="a.json",
            ),
            row("b", nixStatus="outdated", maintainers=[]),
            row("c", updateFailure=True, maintainers=["iedame"]),
            row(
                "haskellPackages.d", pending=True, set="haskellPackages", maintainers=[]
            ),
        ]
        datastore.write(
            {"checkedAt": NOW, "allPackages": True, "packages": rows},
            {"a.json": [nix("a", "1", "newest")]},
            self.out,
        )
        files = {
            os.path.relpath(os.path.join(d, f), self.out)
            for d, _, fs in os.walk(self.out)
            for f in fs
        }
        self.assertEqual(
            files,
            {
                "index.json",
                "names.json",
                "rows/0.json",
                "views/attention.json",
                "views/list/gaming-team.json",
                "views/maintainer/iedame.json",
                "views/maintainer/none.json",
                "views/set/haskellPackages.json",
                "views/team/gaming.json",
            },
        )  # no summary.json, no per-project files
        index = self.read("index.json")
        self.assertNotIn("packages", index)
        self.assertEqual(
            index["counts"],
            {
                "tracked": 3,
                "outdated": 1,
                "failed": 1,
                "vulnerable": 0,
                "updateFailures": 1,
                "waiting": 0,
                "pending": 1,
            },
        )
        self.assertEqual(
            index["views"],
            {
                "attention": 2,
                "teams": {"Gaming": 1},
                "lists": {"gaming-team": 1},
                "sets": {"haskellPackages": 1},
            },
        )
        names = lambda path: [p["name"] for p in self.read(path)["packages"]]  # noqa: E731
        self.assertEqual(names("views/attention.json"), ["b", "c"])
        self.assertEqual(names("views/maintainer/iedame.json"), ["a", "c"])
        self.assertEqual(names("views/maintainer/none.json"), ["b"])  # not pending
        self.assertEqual(
            self.read("names.json")["names"],
            [
                ["a", "u"],
                ["b", "o"],
                ["c", "f"],
                ["haskellPackages.d", "u", "haskellPackages"],
            ],
        )
        # The rows in full, and loaded back as usual.
        self.assertEqual(
            [r["name"] for r in datastore.load(self.out)["packages"]],
            ["a", "b", "c", "haskellPackages.d"],
        )
        self.assertEqual(
            datastore.entries(rows[0], self.out), [nix("a", "1", "newest")]
        )

    def test_newest_repos_kept(self):
        entries = [
            nix("a", "1", "outdated"),
            other("old", "1", "outdated"),
            other("arch", "3", "newest"),
            other("arch", "2", "outdated"),
            other("rolling", "9", "rolling"),
            other("debian", "2", "outdated"),
        ]
        kept = datastore.newest_repos(entries, 2)
        self.assertEqual(
            [(e["repo"], e["version"]) for e in kept],
            [("nix_unstable", "1"), ("arch", "3"), ("debian", "2")],
        )

    def test_entries_kept_in_full_for_the_lists(self):
        many = [nix("a", "1", "newest")] + [
            other(f"r{i}", "1", "newest") for i in range(20)
        ]
        projects = {
            "a": {"dataFile": "a.json", "entries": many},
            "b": {"dataFile": "b.json", "entries": many},
        }
        rows = [
            {"dataFile": "a.json", "lists": ["x"]},
            {"dataFile": "b.json", "lists": []},
        ]
        kept = datastore.kept_entries(projects, rows)
        self.assertEqual(len(kept["a.json"]), 21)
        self.assertEqual(len(kept["b.json"]), 1 + config.REPOLOGY_ENTRIES_KEPT)
