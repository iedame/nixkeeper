"""What carries over from the previous run: its data, for lookups that fail,
when each package became outdated, and since when a source couldn't be
refreshed."""

from . import config, datastore
from .changes import is_outdated
from .sources import repology


def load_previous_run(out_dir=None):
    """The last successful run's index, or an empty one."""
    return datastore.load(out_dir)


def previous_rows(previous, pname, attrs):
    """The last run's rows for a tracked pname (by name, or any of attrs)."""
    return [
        row
        for row in previous["packages"]
        if pname in (row.get("searchTerm"), row["name"])
        or set(attrs) & set(row.get("attrs") or [])
    ]


def new_packages(previous, wanted):
    """How many of wanted ({pname: (attrs, fallback)}, tracking.py) the last
    run didn't have."""
    names = {
        n for row in previous["packages"] for n in (row["name"], row.get("searchTerm"))
    }
    attrs = {a for row in previous["packages"] for a in row.get("attrs") or []}
    return sum(
        1 for p, (a, _) in wanted.items() if p not in names and not set(a) & attrs
    )


def previous_project(previous, pname, attrs, out_dir=None):
    """Reuse the last run's data for a pname (its lookup failed, or isn't due).
    Returns (project, entries, stale_since), or None if there's nothing to
    reuse."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    for row in previous_rows(previous, pname, attrs):
        entries = []
        if row.get("project"):
            try:
                # A file from before trimming has all of Repology's.
                entries = repology.trimmed(datastore.entries(row, out_dir))
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
