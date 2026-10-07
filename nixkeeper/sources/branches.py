"""Hydra's builds of a branch that updates a set before it reaches master,
from nixkeeper-hydra's digest of it (https://github.com/iedame/nixkeeper-
hydra: data/haskell-updates.json.gz): haskell-updates, where the Haskell
team updates haskellPackages (hackage2nix) and merges into master about
every two weeks. A row with a job there gets what the branch has ("branch":
its version, its build and how it went), so the page can say an update is
waiting for the branch's merge, or a failure is fixed there (or isn't). It
changes no count: the branch is a preview of master."""

import gzip
import json
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from . import about, http

FORMAT = 1
# Each branch nixkeeper reads: its file in the hydra digest, and which
# attributes it builds.
BRANCHES = {"haskell-updates": "haskellPackages."}
SYSTEM = "x86_64-linux"  # the branches' jobsets build only it
# A branch's file is read at least daily (when the branch hasn't changed):
# older, nixkeeper-hydra has stopped reading it.
MAX_AGE_HOURS = 48


def wanted(attrs):
    """The branches some of attrs (the tracked ones) are built on."""
    return [
        b for b, prefix in BRANCHES.items() if any(a.startswith(prefix) for a in attrs)
    ]


def load(branch, now):
    """{attr: {"version", "status", "build"}} for branch's jobs on SYSTEM,
    or None (saying why) when the hydra digest is turned off, or the file
    isn't there, isn't current or can't be read."""
    base = config.HYDRA_DIGEST_URL
    if not base:
        return None
    source = f"branch:{branch}"
    try:
        body = http.get_bytes(f"{base}{branch}.json.gz")
        if body is None:
            raise ValueError(f"no {branch}.json.gz yet")
        found = json.loads(gzip.decompress(body))
        if found.get("format") != FORMAT:
            raise ValueError("not in a format this nixkeeper reads")
        at = found["fetchedAt"]
        age = datetime.fromisoformat(now) - datetime.fromisoformat(at)
        if age > timedelta(hours=MAX_AGE_HOURS):
            about.note(source, False, "too old", at=at)
            print(f"::warning::{branch}: not used, read {at}", file=sys.stderr)
            return None
        columns = found["columns"]
        jobs = {}
        for values in found["jobs"]:
            job = dict(zip(columns, values, strict=True))
            if job["system"] != SYSTEM:
                continue
            # What it builds: name-version (Agda-2.8.0.2).
            version = job["name"].rsplit("-", 1)[-1] if "-" in job["name"] else ""
            jobs[job["attr"]] = {
                "version": version,
                "status": job["status"],
                "build": job["build"],
            }
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note(source, False, f"couldn't be read ({e})")
        print(f"::warning::{branch}: couldn't use it ({e})", file=sys.stderr)
        return None
    print(
        f"{branch}: evaluation {found['eval']}, {len(jobs):,} jobs, read {at}",
        file=sys.stderr,
    )
    about.note(source, True, at=at, eval=found["eval"], jobs=len(jobs))
    return jobs


def apply(rows, branch, jobs):
    """Give each row with a job on branch (jobs: load's) what the branch
    has: {"name": branch, "version", "status", "build"}, of its first such
    attribute."""
    if not jobs:
        return
    for row in rows:
        job = next((jobs[a] for a in row.get("attrs") or [] if a in jobs), None)
        if job:
            row["branch"] = {"name": branch, **job}
