"""Hydra's builds of a branch that updates a set before it reaches master,
from nixkeeper-hydra's digest of it (https://github.com/nixkeeper/
digest-builds: data/haskell-updates.json.gz): haskell-updates, where the Haskell
team updates haskellPackages (hackage2nix) and merges into master about
every two weeks. A row with a job there gets what the branch has ("branch":
its version, its build and how it went), so the page can say an update is
waiting for the branch's merge, or a failure is fixed there (or isn't). It
changes no count: the branch is a preview of master.

And staging-next (staging-next.json.gz, its differences from master), for
the updates merged into it (stagingPR): how each builds there, on every
platform, as of Hydra's newest evaluation of it."""

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


# staging-next (since 2026-10-16): all of nixpkgs, its differences from
# master only (digest-builds' branches.py), read for the updates on their
# way there (prs_digest.add_staging_prs) on every platform Hydra builds.
STAGING_NEXT = "staging-next"


def load_staging_next(now):
    """({(attr, system): {"name", "status", "build"}}, {"eval",
    "evaluatedAt"}) of staging-next's newest evaluation, or None (saying
    why) as load."""
    base = config.HYDRA_DIGEST_URL
    if not base:
        return None
    source = f"branch:{STAGING_NEXT}"
    try:
        body = http.get_bytes(f"{base}{STAGING_NEXT}.json.gz")
        if body is None:
            raise ValueError(f"no {STAGING_NEXT}.json.gz yet")
        found = json.loads(gzip.decompress(body))
        if found.get("format") != FORMAT:
            raise ValueError("not in a format this nixkeeper reads")
        at = found["fetchedAt"]
        age = datetime.fromisoformat(now) - datetime.fromisoformat(at)
        if age > timedelta(hours=MAX_AGE_HOURS):
            about.note(source, False, "too old", at=at)
            print(f"::warning::{STAGING_NEXT}: not used, read {at}", file=sys.stderr)
            return None
        columns = found["columns"]
        jobs = {}
        for values in found["jobs"]:
            job = dict(zip(columns, values, strict=True))
            jobs[job["attr"], job["system"]] = {
                "name": job["name"],
                "status": job["status"],
                "build": job["build"],
            }
        info = {"eval": found["eval"], "evaluatedAt": found.get("evaluatedAt")}
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note(source, False, f"couldn't be read ({e})")
        print(f"::warning::{STAGING_NEXT}: couldn't use it ({e})", file=sys.stderr)
        return None
    print(
        f"{STAGING_NEXT}: evaluation {found['eval']} "
        f"({info['evaluatedAt'] or 'date unknown'}), {len(jobs):,} jobs differing "
        f"from master, read {at}",
        file=sys.stderr,
    )
    about.note(source, True, at=at, jobs=len(jobs), **info)
    return jobs, info


def apply_staging_next(rows, found):
    """Give each row's update on staging-next (its stagingPR "on"
    staging-next) how it builds there, from found (load_staging_next's):
    "builds", [{"system", "status", "build"}] of its attributes' jobs at
    the PR's version, or none when the evaluation hasn't that version yet
    (merged since: "inEval" false); and "eval", which evaluation and when."""
    if not found:
        return
    jobs, info = found
    by_attr = {}
    for (attr, system), job in jobs.items():
        by_attr.setdefault(attr, []).append({"system": system, **job})
    for row in rows:
        pr = row.get("stagingPR")
        if not pr or pr.get("on") != STAGING_NEXT:
            continue
        theirs = [j for a in row.get("attrs") or [] for j in by_attr.get(a, [])]
        # At the PR's version: what it builds, name-version (imagemagick-
        # 7.1.2-34, python3.13-hatchling-1.32.0).
        at = [j for j in theirs if j["name"].endswith(f"-{pr['to']}")]
        pr["eval"] = info
        pr["inEval"] = bool(at)
        # Each platform once: its first attribute's job (heroic's, not
        # heroic-unwrapped's too).
        builds = {}
        for j in at:
            builds.setdefault(
                j["system"],
                {"system": j["system"], "status": j["status"], "build": j["build"]},
            )
        pr["builds"] = sorted(builds.values(), key=lambda b: b["system"])


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
