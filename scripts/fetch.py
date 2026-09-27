#!/usr/bin/env python3
"""Fetch Repology status for every package listed in packages.nix.

Writes one raw JSON file per package to data/<name>.json, plus a
data/index.json summary focused on the nix_unstable status of each.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OUT_DIR = "data"
NIX_REPO = "nix_unstable"
USER_AGENT = "pkgwatch/1.0 (personal package tracker)"


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
    url = f"https://repology.org/api/v1/project/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    packages = read_packages()
    index = []

    for name in packages:
        print(f"Fetching {name}...", file=sys.stderr)
        entries = fetch_project(name)

        with open(os.path.join(OUT_DIR, f"{name}.json"), "w") as f:
            json.dump(entries, f, indent=2, sort_keys=True)

        nix = next((e for e in entries if e.get("repo") == NIX_REPO), None)
        others = [e for e in entries if e.get("repo") != NIX_REPO]
        ref = next((e.get("version") for e in others if e.get("status") == "newest"), None)

        index.append({
            "name": name,
            "nixVersion": nix.get("version") if nix else None,
            "nixStatus": nix.get("status") if nix else "missing",
            "refVersion": ref,
            "repoCount": len(others),
        })
        time.sleep(1)  # be polite to Repology's API

    with open(os.path.join(OUT_DIR, "index.json"), "w") as f:
        json.dump({
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "packages": index,
        }, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
