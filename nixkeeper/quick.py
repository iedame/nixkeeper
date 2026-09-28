"""The quick check: the update checks marked `frequent = true` in
package-lists/update-checks.nix, run hourly for packages where a new release
matters within the hour (browsers, for their security fixes). Starts from the
last published data and touches only those packages: their Repology data
(so the comparison uses nixpkgs' current version) and their update check.
Writes data/ and updates the status issue only if something changed.
Run from the repository root: `nix run .#quick-check`."""

import copy
import sys
import urllib.error
from datetime import UTC, datetime

from . import history, notify, output, rows
from .sources import nixpkgs as nixpkgs_source
from .sources import repology, upstream

# Fields a run sets from scratch, so a copy of last run's row mustn't keep
# them: each is set again below if it still applies.
REFRESHED = ("upstream", "outdatedSince")


def refresh_repology(row, previous, now):
    """Update row's nixpkgs version and status from Repology. Returns the
    project's entries to write to its data file, or None if the lookup failed
    (row then keeps its data, marked as not refreshed like in a full sync)."""
    try:
        project, entries = repology.project_by_name(row["project"])
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(
            f"::warning::{row['name']}: Repology lookup failed ({e})", file=sys.stderr
        )
        row["staleSince"] = row.get("staleSince") or previous.get("checkedAt") or now
        return None
    if project is None:
        return None  # renamed on Repology: the daily sync will sort it out
    proj = {
        "name": row["name"],
        "project": project,
        "attrs": row["attrs"],
        "entries": entries,
        "dataFile": row["dataFile"],
    }
    # nixpkgs isn't loaded ({}): platforms and homepage stay as they were.
    fresh = next(
        (r for r in rows.project_rows(proj, {}) if r["name"] == row["name"]), None
    )
    if fresh is None:
        return None
    for key in ("nixVersion", "nixStatus", "nixVulnerable", "refVersion", "repoCount"):
        row[key] = fresh[key]
    row.pop("staleSince", None)
    return entries


def meaningful(packages):
    """packages without what changes every run anyway (when a check last
    succeeded), to tell whether anything worth publishing changed."""
    packages = copy.deepcopy(packages)
    for row in packages:
        (row.get("upstream") or {}).pop("checkedAt", None)
    return packages


def main():
    now = datetime.now(UTC).isoformat()
    previous = history.load_previous_run()
    if not previous["packages"]:
        sys.exit("No previous run in data/: run the full sync first (nix run .#sync).")
    checks = {
        name: check
        for name, check in (
            nixpkgs_source.read_lists().get("updateChecks") or {}
        ).items()
        if check.get("frequent")
    }
    packages = copy.deepcopy(previous["packages"])
    by_name = {row["name"]: row for row in packages}
    selected = [by_name[name] for name in checks if name in by_name]
    if not selected:
        print("No frequent update checks for tracked packages.", file=sys.stderr)
        return
    print(f"Quick check: {', '.join(row['name'] for row in selected)}", file=sys.stderr)
    data_files = {}
    for row in selected:
        for key in REFRESHED:
            row.pop(key, None)
        stale = row.get("notRefreshed") or {}
        stale.pop("upstream", None)
        if not stale:
            row.pop("notRefreshed", None)
        if row.get("project"):
            entries = refresh_repology(row, previous, now)
            if entries is not None:
                data_files[row["dataFile"]] = entries
    upstream.add_checks(selected, checks, previous, now)
    history.add_outdated_since(selected, previous, now)

    if meaningful(packages) == meaningful(previous["packages"]):
        print("Nothing changed.", file=sys.stderr)
        return
    # checkedAt stays the full sync's: it's what the page's staleness warning
    # and the sources the quick check doesn't touch go by.
    index = {**previous, "packages": packages}
    output.update({**data_files, "index.json": index})
    print("Changes written.", file=sys.stderr)
    notify.notify(previous, packages, now)


if __name__ == "__main__":
    main()
