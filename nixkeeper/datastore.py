"""Reading and writing data/, the page's data. Everything that reads the
previous run (history, schedules, notifications, the hourly checks) or
writes a new one goes through here.

Two formats (docs/data.md):

- format 1: index.json with every row in full ("packages"), and each
  Repology project's entries in <dataFile> (output of 0.11.0 and before);
- format 2: index.json as a small manifest (format, counts), summary.json
  with a short entry per row (what the page's list needs), and the full rows
  in rows/<n>.json shards (n from a hash of the name), each row with its
  Repology entries ("repology").

While pages switch over, both are written: format 2 beside format 1 (its
"packages" and per-project files), so a page from before still works."""

import contextlib
import copy
import functools
import json
import math
import os
import re
import shutil
import zlib

from . import config

FORMAT = 2
# Rows a shard holds, about: a shard is what a details panel loads.
SHARD_ROWS = 500
# A row's fields only the details panels use, left out of its summary entry.
PANEL_ONLY = ("dataFile", "homepage", "repoCount", "repologyCheckedAt", "source")
# Of a summary entry's update check, what the list shows (the version,
# whether it's newer, whose check it is).
UPSTREAM_SHOWN = ("community", "inferred", "newer", "version")


def data_file(key):
    """File name for a project's Repology data: names like python:requests
    contain characters that don't belong in file names or URLs."""
    return re.sub(r"[^A-Za-z0-9._+-]", "_", key) + ".json"


def dumps(data):
    """data as compact JSON (no indentation), keys sorted: about a third
    smaller than indented, and the same bytes whenever the data is the same."""
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def shard_count(rows):
    """How many shards for rows: about SHARD_ROWS a shard, rounded up to a
    power of two (1 for a few hundred, 256 for all of nixpkgs)."""
    return 1 << max(0, math.ceil(math.log2(max(1, rows / SHARD_ROWS))))


def shard_of(name, count):
    """The shard a row is in: a stable hash of its name, so adding a package
    changes only its own shard."""
    return zlib.crc32(name.encode()) % count


def elided(row, run):
    """row as written: its stamps from this run (each build's and its update
    check's "checkedAt", its "countedAt") left out when they're run, the
    index's checkedAt, so a row nothing new happened to keeps its bytes from
    run to run. restored() puts them back."""
    if not run:
        return row
    row = dict(row)
    if row.get("countedAt") == run:
        del row["countedAt"]
    if (row.get("upstream") or {}).get("checkedAt") == run:
        row["upstream"] = {k: v for k, v in row["upstream"].items() if k != "checkedAt"}
    if "builds" in row:
        row["builds"] = [
            {k: v for k, v in b.items() if k != "checkedAt"}
            if b.get("checkedAt") == run
            else b
            for b in row["builds"]
        ]
    return row


def restored(row, run):
    """row as elided() wrote it, with its stamps back: each is always there
    when what it dates is (every build and update check has one, and counts
    have theirs), so a missing one was run's."""
    if not run:
        return row
    for build in row.get("builds") or []:
        build.setdefault("checkedAt", run)
    if row.get("upstream"):
        row["upstream"].setdefault("checkedAt", run)
    if "openPRs" in row:
        row.setdefault("countedAt", run)
    return row


def summary_entry(row):
    """row's entry in summary.json: what the list, the counts, filters,
    search and sorting need. Builds are reduced to their status and
    platform, the update attempt to its outcome."""
    entry = {k: v for k, v in row.items() if k not in PANEL_ONLY}
    if "builds" in row:
        entry["builds"] = [
            {"status": b["status"], "system": b["system"]} for b in row["builds"]
        ]
    if row.get("update"):  # null (never tried) and missing (not in nixpkgs) kept
        entry["update"] = {"outcome": row["update"].get("outcome")}
    if "upstream" in row:
        entry["upstream"] = {
            k: v for k, v in row["upstream"].items() if k in UPSTREAM_SHOWN
        }
    return entry


def files(index, entries):
    """Every file of data/ for index (its rows in "packages") and entries
    (Repology's, by dataFile): {path in data/: data}."""
    run = index.get("checkedAt")
    given = [elided(row, run) for row in index["packages"]]  # format 1's order
    rows = sorted(given, key=lambda row: row["name"])
    count = shard_count(len(rows))
    shards = [[] for _ in range(count)]
    for row in rows:
        full = dict(row)
        if found := entries.get(row.get("dataFile")):
            full["repology"] = found
        shards[shard_of(row["name"], count)].append(full)
    out = {name: data for name, data in entries.items()}  # format 1
    out["index.json"] = {
        **index,
        "packages": given,
        "format": FORMAT,
        "packageCount": len(rows),
        "shardCount": count,
    }
    out["summary.json"] = {"packages": [summary_entry(row) for row in rows]}
    for n, shard in enumerate(shards):
        out[f"rows/{n}.json"] = {"packages": shard}
    return out


def _write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def write(index, entries, out_dir=None):
    """Write data/ for index and entries (files). Built from scratch in a
    temporary folder and only then swapped in for out_dir, so removed
    packages disappear and a failed run leaves the previous data intact."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    tmp_dir = out_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)  # leftover from a failed run
    os.makedirs(tmp_dir)
    for name, data in files(index, entries).items():
        _write_file(os.path.join(tmp_dir, name), dumps(data))
    shutil.rmtree(out_dir, ignore_errors=True)
    os.rename(tmp_dir, out_dir)


def update(index, entries, out_dir=None):
    """Rewrite data/ in place for index and entries (files), only the files
    whose content changed, each written aside first so a failure never
    leaves one half-written. For partial runs (the hourly checks), which
    change a few rows."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    for name, data in files(index, entries).items():
        path = os.path.join(out_dir, name)
        text = dumps(data)
        try:
            with open(path) as f:
                if f.read() == text:
                    continue
        except OSError:
            pass
        _write_file(path, text)


def _load(path):
    with open(path) as f:
        return json.load(f)


@functools.lru_cache(maxsize=64)
def _cached(path, changed):
    """A data file's JSON, read once while it's unchanged (changed: its
    modification time): entries() reads a shard for each of its rows."""
    return _load(path)


def _shared(path):
    """A data file's JSON from the cache: not to be changed."""
    return _cached(path, os.stat(path).st_mtime_ns)


def load(out_dir=None):
    """The last run's index, with every row in "packages" (without their
    Repology entries: entries()), whichever format it was written in; an
    empty one if there's none or it can't be read."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    try:
        index = _load(os.path.join(out_dir, "index.json"))
    except (OSError, ValueError):
        return {"packages": []}
    if index.get("format") == FORMAT:
        # The rows from the shards; if one can't be read, format 1's (below).
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
            index["packages"] = sorted(
                (
                    {k: v for k, v in row.items() if k != "repology"}
                    for n in range(index["shardCount"])
                    for row in _load(os.path.join(out_dir, f"rows/{n}.json"))[
                        "packages"
                    ]
                ),
                key=lambda row: row["name"],
            )
    index.setdefault("packages", [])
    for row in index["packages"]:
        restored(row, index.get("checkedAt"))
    return index


def entries(row, out_dir=None):
    """row's Repology entries from the last run: from its shard (format 2),
    else its data file (format 1). Raises OSError or ValueError when neither
    can be read."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    try:
        index = _shared(os.path.join(out_dir, "index.json"))
        if index.get("format") == FORMAT:
            n = shard_of(row["name"], index["shardCount"])
            for full in _shared(os.path.join(out_dir, f"rows/{n}.json"))["packages"]:
                if full["name"] == row["name"]:
                    return copy.deepcopy(full.get("repology") or [])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    path = os.path.join(out_dir, row.get("dataFile") or f"{row['project']}.json")
    with open(path) as f:
        return json.load(f)
