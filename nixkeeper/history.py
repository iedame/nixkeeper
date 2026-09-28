"""What carries over from the previous run: its data, for lookups that fail,
when each package became outdated, and since when a source couldn't be
refreshed."""

import json
import os

from . import config
from .changes import is_outdated


def load_previous_run(out_dir=None):
    """The last successful run's index, or an empty one."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    try:
        with open(os.path.join(out_dir, "index.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"packages": []}


def previous_project(previous, pname, attrs, out_dir=None):
    """Reuse the last run's data for a pname whose lookup failed. Returns
    (project, entries, stale_since), or None if there's nothing to reuse."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    for row in previous["packages"]:
        if pname in (row.get("searchTerm"), row["name"]) or set(attrs) & set(
            row.get("attrs") or []
        ):
            entries = []
            if row.get("project"):
                try:
                    with open(
                        os.path.join(
                            out_dir, row.get("dataFile") or f"{row['project']}.json"
                        )
                    ) as f:
                        entries = json.load(f)
                except (OSError, ValueError):
                    return None
            return (
                row.get("project"),
                entries,
                row.get("staleSince") or previous.get("checkedAt"),
            )
    return None


def not_refreshed(row, source, reason, before, now):
    """Record that source ("builds", "update" or "upstream") couldn't be
    refreshed for row this run, so what it shows is the previous run's (or
    nothing). before is the row's previous-run version, if any: the date it
    started failing carries over, so "since" stays the first failing run."""
    since = ((before or {}).get("notRefreshed") or {}).get(source, {}).get("since")
    row.setdefault("notRefreshed", {})[source] = {
        "since": since or now,
        "reason": reason,
    }


def add_outdated_since(rows, previous, now):
    """Mark when each outdated row first became outdated. Neither Repology nor
    nixpkgs has that date, so it's carried from run to run: kept while the row
    stays outdated (even if nixpkgs updates but is still behind), set to now
    when it newly falls behind, dropped once it's caught up."""
    before = {row["name"]: row for row in previous["packages"]}
    for row in rows:
        if is_outdated(row):
            row["outdatedSince"] = (
                before.get(row["name"], {}).get("outdatedSince") or now
            )
