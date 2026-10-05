import json
import os
import tempfile
import unittest

from nixkeeper import datastore
from nixkeeper.datastore import data_file, write

ENTRIES = [{"repo": "nix_unstable", "version": "1.18.5"}]


def full_row(name, **extra):
    """A row as the sync writes it, with fields only the panels use."""
    return {
        "name": name,
        "project": name,
        "dataFile": f"{name}.json",
        "homepage": "https://example.org",
        "source": "https://github.com/NixOS/nixpkgs/blob/x/package.nix#L1",
        "repoCount": 12,
        "repologyCheckedAt": "2026-10-05T00:00:00+00:00",
        "nixVersion": "1.18.5",
        "builds": [
            {
                "attr": name,
                "build": 1,
                "checkedAt": "2026-10-05T06:00:00+00:00",
                "name": f"{name}-1.18.5",
                "status": "failed",
                "system": "x86_64-linux",
                "version": "1.18.5",
            }
        ],
        "update": {"outcome": "failed", "log": "https://example.org/log", "to": "2"},
        "upstream": {
            "version": "1.19",
            "newer": True,
            "repo": "wesnoth/wesnoth",
            "checkedAt": "2026-10-05T06:00:00+00:00",
        },
        **extra,
    }


class Output(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = os.path.join(self.dir.name, "data")

    def read(self, name):
        with open(os.path.join(self.out, name)) as f:
            return f.read()

    def test_data_file_is_safe(self):
        self.assertEqual(data_file("python:requests"), "python_requests.json")
        self.assertEqual(data_file("wesnoth"), "wesnoth.json")
        self.assertEqual(data_file("a/b c"), "a_b_c.json")

    def test_write_replaces_the_whole_folder(self):
        os.makedirs(self.out)
        with open(os.path.join(self.out, "removed-package.json"), "w") as f:
            f.write("[]")
        os.makedirs(self.out + ".tmp")  # leftover from a failed run
        write(
            {"checkedAt": "now", "packages": [full_row("wesnoth")]},
            {"wesnoth.json": [{"repo": "x"}]},
            self.out,
        )
        self.assertEqual(
            sorted(os.listdir(self.out)),
            ["index.json", "rows", "summary.json", "wesnoth.json"],
        )
        self.assertEqual(os.listdir(os.path.join(self.out, "rows")), ["0.json"])
        self.assertFalse(os.path.exists(self.out + ".tmp"))
        self.assertEqual(json.loads(self.read("wesnoth.json")), [{"repo": "x"}])

    def test_written_compact_with_sorted_keys(self):
        write({"packages": [{"name": "a"}], "checkedAt": "now"}, {}, self.out)
        self.assertEqual(self.read("summary.json"), '{"packages":[{"name":"a"}]}')
        self.assertTrue(self.read("index.json").startswith('{"checkedAt":"now",'))

    def test_manifest_keeps_format_1_rows(self):
        rows = [full_row("wesnoth"), full_row("unciv")]
        write({"checkedAt": "now", "version": "0.12.0", "packages": rows}, {}, self.out)
        index = json.loads(self.read("index.json"))
        self.assertEqual(index["format"], 2)
        self.assertEqual(index["packageCount"], 2)
        self.assertEqual(index["shardCount"], 1)
        self.assertEqual(index["version"], "0.12.0")
        # A page from before reads these, until it's updated.
        self.assertEqual(
            [row["name"] for row in index["packages"]], ["wesnoth", "unciv"]
        )

    def test_summary_leaves_out_what_only_panels_use(self):
        write({"packages": [full_row("wesnoth", openPRs=2)]}, {}, self.out)
        (entry,) = json.loads(self.read("summary.json"))["packages"]
        for key in datastore.PANEL_ONLY:
            self.assertNotIn(key, entry)
        self.assertEqual(
            entry["builds"], [{"status": "failed", "system": "x86_64-linux"}]
        )
        self.assertEqual(entry["update"], {"outcome": "failed"})
        self.assertEqual(entry["upstream"], {"version": "1.19", "newer": True})
        self.assertEqual(entry["openPRs"], 2)
        self.assertEqual(entry["nixVersion"], "1.18.5")

    def test_summary_keeps_null_and_missing_update_apart(self):
        never = {"name": "a", "update": None}  # the bot never tried
        absent = {"name": "b"}  # not in nixpkgs
        write({"packages": [never, absent]}, {}, self.out)
        a, b = json.loads(self.read("summary.json"))["packages"]
        self.assertIsNone(a["update"])
        self.assertNotIn("update", b)

    def test_shards_hold_full_rows_with_their_entries(self):
        write(
            {"packages": [full_row("wesnoth"), full_row("unciv")]},
            {"wesnoth.json": ENTRIES, "unciv.json": []},
            self.out,
        )
        rows = json.loads(self.read("rows/0.json"))["packages"]
        self.assertEqual([row["name"] for row in rows], ["unciv", "wesnoth"])
        self.assertNotIn("repology", rows[0])  # no entries: left out
        self.assertEqual(rows[1]["repology"], ENTRIES)
        self.assertEqual(rows[1]["builds"][0]["build"], 1)  # in full

    def test_shard_count(self):
        self.assertEqual(datastore.shard_count(0), 1)
        self.assertEqual(datastore.shard_count(241), 1)
        self.assertEqual(datastore.shard_count(501), 2)
        self.assertEqual(datastore.shard_count(1500), 4)
        self.assertEqual(datastore.shard_count(150_000), 512)

    def test_shards_by_name_hash(self):
        rows = [{"name": f"pkg{i}"} for i in range(1200)]
        write({"packages": rows}, {}, self.out)
        index = json.loads(self.read("index.json"))
        self.assertEqual(index["shardCount"], 4)
        seen = []
        for n in range(4):
            shard = json.loads(self.read(f"rows/{n}.json"))["packages"]
            self.assertTrue(shard)  # spread out
            for row in shard:
                self.assertEqual(datastore.shard_of(row["name"], 4), n)
            seen += [row["name"] for row in shard]
        self.assertEqual(sorted(seen), sorted(row["name"] for row in rows))

    def test_load_reads_format_2_shards(self):
        rows = [full_row("wesnoth"), full_row("unciv")]
        write(
            {"checkedAt": "now", "packages": rows}, {"wesnoth.json": ENTRIES}, self.out
        )
        index = json.loads(self.read("index.json"))
        index.pop("packages")  # as once format 1 isn't written anymore
        with open(os.path.join(self.out, "index.json"), "w") as f:
            json.dump(index, f)
        loaded = datastore.load(self.out)
        self.assertEqual(loaded["checkedAt"], "now")
        self.assertEqual(
            loaded["packages"], sorted(rows, key=lambda row: row["name"])
        )  # without their entries

    def test_load_reads_format_1(self):
        os.makedirs(self.out)
        with open(os.path.join(self.out, "index.json"), "w") as f:
            json.dump({"checkedAt": "then", "packages": [{"name": "a"}]}, f, indent=2)
        self.assertEqual(
            datastore.load(self.out), {"checkedAt": "then", "packages": [{"name": "a"}]}
        )

    def test_load_without_data(self):
        self.assertEqual(datastore.load(self.out), {"packages": []})

    def test_entries_from_the_shard_then_the_data_file(self):
        row = full_row("wesnoth")
        write({"packages": [row]}, {"wesnoth.json": ENTRIES}, self.out)
        os.remove(os.path.join(self.out, "wesnoth.json"))
        self.assertEqual(datastore.entries(row, self.out), ENTRIES)
        # Format 1 (from 0.11.0 and before): the data file.
        os.makedirs(os.path.join(self.dir.name, "old"))
        old = os.path.join(self.dir.name, "old")
        with open(os.path.join(old, "index.json"), "w") as f:
            json.dump({"packages": [row]}, f)
        with open(os.path.join(old, "wesnoth.json"), "w") as f:
            json.dump(ENTRIES, f)
        self.assertEqual(datastore.entries(row, old), ENTRIES)
        with self.assertRaises(OSError):
            datastore.entries(full_row("unciv"), old)

    def test_update_rewrites_only_what_changed(self):
        rows = [{"name": f"pkg{i}"} for i in range(1200)]
        write({"packages": rows}, {}, self.out)
        before = {
            n: os.stat(os.path.join(self.out, f"rows/{n}.json")).st_mtime_ns
            for n in range(4)
        }
        changed = [dict(row) for row in rows]
        changed[0]["nixVersion"] = "2"
        datastore.update({"packages": changed}, {}, self.out)
        shard = datastore.shard_of("pkg0", 4)
        for n in range(4):
            after = os.stat(os.path.join(self.out, f"rows/{n}.json")).st_mtime_ns
            self.assertEqual(after != before[n], n == shard, n)
        self.assertEqual(datastore.load(self.out)["packages"][0]["nixVersion"], "2")
