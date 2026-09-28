"""Looking up tracked packages on Repology, with fallback to the last run."""
import sys
import urllib.error

from . import config, history
from .output import data_file
from .sources import repology


def collect_projects(wanted, previous, resolve=repology.resolve, out_dir=config.OUT_DIR):
    """Look up every tracked package on Repology, falling back to the previous
    run's data (in out_dir) when a lookup fails. Several attrs (wesnoth /
    wesnoth-devel, heroic / heroic-unwrapped) can map to one project; those
    are merged here and split into rows by rows.project_rows. Returns project
    -> {"name", "project", "attrs", "entries", "dataFile"[, "staleSince"]}, or
    exits if too many lookups failed."""
    projects = {}
    failed = []
    for pname, (attrs, fallback) in sorted(wanted.items()):
        print(f"Resolving {pname}...", file=sys.stderr)
        stale_since = None
        try:
            project, entries = resolve(fallback, attrs)
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(pname)
            reused = history.previous_project(previous, pname, attrs, out_dir)
            if not reused:
                print(f"  giving up on {pname} ({e}); no previous data, skipping it this run", file=sys.stderr)
                continue
            project, entries, stale_since = reused
            print(f"  giving up on {pname} ({e}); reusing data from {stale_since}", file=sys.stderr)

        key = project or pname
        if key in projects:
            projects[key]["attrs"] += [a for a in attrs if a not in projects[key]["attrs"]]
            continue
        projects[key] = {"name": pname, "project": project, "attrs": attrs,
                         "entries": entries or [], "dataFile": data_file(key)}
        if stale_since:
            projects[key]["staleSince"] = stale_since

    if len(failed) > config.MAX_FAILED_SHARE * len(wanted):
        sys.exit(f"Repology lookups failed for {len(failed)} of {len(wanted)} packages; "
                 f"keeping the previous data. Failed: {', '.join(failed)}")
    return projects
