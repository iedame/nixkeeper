"""Hydra client: the latest build of each tracked package on each platform."""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from .. import config

# Hydra's buildstatus codes. 1 and 6 ("failed with output") are the package's
# own failure; 2 is a dependency's. Anything else (aborted, cancelled, timed
# out, log or output limit exceeded, ...) means the build didn't finish.
FAILED = {1, 6}
DEPENDENCY_FAILED = 2


def get(path):
    """GET a Hydra path as JSON, retrying after RETRY_DELAYS seconds. Returns
    None on 404."""
    last_err = None
    for delay in [0, *config.RETRY_DELAYS]:
        if delay:
            print(f"  retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)
        req = urllib.request.Request(
            config.HYDRA_URL + path,
            headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            e.close()  # an HTTP error is also an open response
            if e.code == 404:
                return None
            print(f"  Hydra answered {e.code}", file=sys.stderr)
            last_err = e
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"  Hydra request failed ({e})", file=sys.stderr)
            last_err = e
    raise last_err


def status(buildstatus):
    if buildstatus == 0:
        return "ok"
    if buildstatus in FAILED:
        return "failed"
    if buildstatus == DEPENDENCY_FAILED:
        return "dependency"
    return "unfinished"


def job_url(job):
    return f"{config.HYDRA_URL}/job/{config.HYDRA_PROJECT}/{config.HYDRA_JOBSET}/{job}"


def latest_build(job):
    """The job's most recent finished build, or None if Hydra has none."""
    query = urllib.parse.urlencode(
        {
            "nr": 1,
            "project": config.HYDRA_PROJECT,
            "jobset": config.HYDRA_JOBSET,
            "job": job,
        }
    )
    builds = get(f"/api/latestbuilds?{query}")
    return builds[0] if builds else None


def last_success(job):
    """When the job last built successfully (ISO date), or None if never."""
    build = get(f"/job/{config.HYDRA_PROJECT}/{config.HYDRA_JOBSET}/{job}/latest")
    stoptime = (build or {}).get("stoptime")
    return datetime.fromtimestamp(stoptime, UTC).isoformat() if stoptime else None


def check(attr, system, broken=False):
    """One job's result: {"attr", "system", "status", "build"?, "lastSuccess"?}.
    status is ok / failed / dependency / unfinished, notBuilt when Hydra has no
    build of it, or broken when nixpkgs marks it broken there (whatever Hydra's
    last build did: the failure is known)."""
    job = f"{attr}.{system}"
    result = {"attr": attr, "system": system}
    build = latest_build(job)
    time.sleep(1)  # be polite to Hydra
    if build is None:
        return {**result, "status": "broken" if broken else "notBuilt"}
    result.update(status=status(build.get("buildstatus")), build=build["id"])
    if broken or result["status"] == "failed":
        result["lastSuccess"] = last_success(job)
        time.sleep(1)
    if broken:
        result["status"] = "broken"
    return result


def is_unfree(pkg):
    """Hydra doesn't build unfree packages, so there's nothing to ask about."""
    meta = pkg["meta"]
    if meta.get("unfree"):
        return True
    licenses = meta.get("license") or []
    if not isinstance(licenses, list):
        licenses = [licenses]
    return any(isinstance(lic, dict) and lic.get("free") is False for lic in licenses)


def systems(pkg):
    """Hydra platforms the package claims to build on: all of them when it
    doesn't declare meta.platforms, none when meta.hydraPlatforms is empty."""
    meta = pkg["meta"]
    wanted = config.HYDRA_SYSTEMS
    if meta.get("platforms"):
        wanted = [s for s in wanted if s in meta["platforms"]]
    if meta.get("hydraPlatforms") is not None:
        wanted = [s for s in wanted if s in meta["hydraPlatforms"]]
    return wanted


def add_builds(rows, nixpkgs, previous, broken=None):
    """Give every row in nixpkgs its Hydra results ("builds"), or mark it unfree
    ("unfree": true, no builds). broken: {attr: [systems]} nixpkgs marks
    broken. A job whose lookup fails keeps the previous run's result, if there
    is one."""
    broken = broken or {}
    print("Checking Hydra builds...", file=sys.stderr)
    before = {
        (b["attr"], b["system"]): b
        for row in previous["packages"]
        for b in row.get("builds") or []
    }
    failed = consecutive = 0
    for row in rows:
        pkgs = {a: nixpkgs[a] for a in row["attrs"] if a in nixpkgs}
        if not pkgs:
            continue  # not in nixpkgs: nothing Hydra could build
        free = {a: p for a, p in pkgs.items() if not is_unfree(p)}
        if not free:
            row["unfree"] = True
            row["builds"] = []
            continue
        builds = []
        for attr, pkg in free.items():
            for system in systems(pkg):
                is_broken = system in broken.get(attr, [])
                down = consecutive >= config.HYDRA_MAX_CONSECUTIVE_FAILURES
                try:
                    if down:
                        raise OSError("Hydra seems down, not asking")
                    builds.append(check(attr, system, is_broken))
                    consecutive = 0
                except (urllib.error.URLError, OSError, ValueError) as e:
                    failed += 1
                    consecutive += not down
                    if not down:
                        print(f"  {attr}.{system}: {e}", file=sys.stderr)
                    build = dict(
                        before.get((attr, system))
                        or {"attr": attr, "system": system, "status": "unknown"}
                    )
                    if is_broken:
                        build["status"] = "broken"
                    builds.append(build)
        row["builds"] = builds
    if failed:
        print(
            f"::warning::{failed} Hydra lookups failed; those show the previous "
            "run's result (or unknown)",
            file=sys.stderr,
        )
