#!/usr/bin/env python3
"""Fetch Repology status for every package listed in packages.nix.

Writes one raw JSON file per package to data/<name>.json, plus a
data/index.json summary focused on the nix_unstable status of each.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OUT_DIR = "data"
# Built from scratch each run, then swapped in for OUT_DIR only once every
# fetch succeeded, so removed packages disappear and a failed run leaves the
# previous data intact.
TMP_DIR = OUT_DIR + ".tmp"
NIX_REPO = "nix_unstable"
USER_AGENT = "nixkeeper/1.0 (personal package tracker)"
# repology.org has occasionally been unreachable; repology.amdmi3.ru (the
# author's own domain) has served as a working fallback. Tried in order;
# set REPOLOGY_BASE_URL to force a single one instead.
override = os.environ.get("REPOLOGY_BASE_URL")
BASE_URLS = [override] if override else ["https://repology.org", "https://repology.amdmi3.ru"]


def read_packages():
    result = subprocess.run(
        [
            "nix", "eval",
            "--extra-experimental-features", "nix-command flakes",
            "--json", "-f", "packages.nix",
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def fetch_project(name):
    last_err = None
    for base in BASE_URLS:
        url = f"{base}/api/v1/project/{name}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            last_err = e
        except (urllib.error.URLError, OSError) as e:
            print(f"  {base} unreachable ({e}), trying next domain...", file=sys.stderr)
            last_err = e
    raise last_err


def main():
    shutil.rmtree(TMP_DIR, ignore_errors=True)  # leftover from a failed run
    os.makedirs(TMP_DIR)
    packages = read_packages()
    index = []

    for name in packages:
        print(f"Fetching {name}...", file=sys.stderr)
        entries = fetch_project(name)

        with open(os.path.join(TMP_DIR, f"{name}.json"), "w") as f:
            json.dump(entries, f, indent=2, sort_keys=True)

        nix = next((e for e in entries if e.get("repo") == NIX_REPO), None)
        others = [e for e in entries if e.get("repo") != NIX_REPO]
        ref = next((e.get("version") for e in others if e.get("status") == "newest"), None)

        index.append({
            "name": name,
            "nixVersion": nix.get("version") if nix else None,
            "nixStatus": nix.get("status") if nix else "missing",
            "nixVulnerable": bool(nix.get("vulnerable")) if nix else False,
            "refVersion": ref,
            "repoCount": len(others),
        })
        time.sleep(1)  # be polite to Repology's API

    with open(os.path.join(TMP_DIR, "index.json"), "w") as f:
        json.dump({
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "packages": index,
        }, f, indent=2, sort_keys=True)

    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.rename(TMP_DIR, OUT_DIR)


if __name__ == "__main__":
    main()
