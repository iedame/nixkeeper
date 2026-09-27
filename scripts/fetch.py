#!/usr/bin/env python3
"""Fetch Repology status for every package tracked in package-lists/.

The tracked set is every nixpkgs package whose meta.maintainers includes one
of the GitHub handles in package-lists/default.nix, plus every pname from the
lists it imports. Each is looked up on Repology via its nixpkgs attribute name.

Writes one raw JSON file per Repology project to data/<project>.json, plus a
data/index.json summary focused on the nix_unstable status of each.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import brotli

OUT_DIR = "data"
# Built from scratch each run, then swapped in for OUT_DIR only once every
# fetch succeeded, so removed packages disappear and a failed run leaves the
# previous data intact.
TMP_DIR = OUT_DIR + ".tmp"
LISTS_DIR = "package-lists"
NIX_REPO = "nix_unstable"
# Every package in nixos-unstable with its meta (maintainers, platforms, ...).
# Same channel Repology's nix_unstable tracks, and far cheaper than evaluating
# nixpkgs ourselves.
NIXPKGS_INDEX_URL = "https://channels.nixos.org/nixos-unstable/packages.json.br"
USER_AGENT = "nixkeeper/1.0 (personal package tracker)"
# repology.org has occasionally been unreachable; repology.amdmi3.ru (the
# author's own domain) has served as a working fallback. Tried in order;
# set REPOLOGY_BASE_URL to force a single one instead.
override = os.environ.get("REPOLOGY_BASE_URL")
BASE_URLS = [override] if override else ["https://repology.org", "https://repology.amdmi3.ru"]


def read_lists():
    result = subprocess.run(
        [
            "nix", "eval",
            "--extra-experimental-features", "nix-command flakes",
            "--json", "-f", LISTS_DIR,
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def load_nixpkgs_index():
    print("Downloading nixpkgs package index...", file=sys.stderr)
    req = urllib.request.Request(NIXPKGS_INDEX_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        packages = json.loads(brotli.decompress(resp.read()))["packages"]
    # Only top-level attributes: a pname like "heroic" would otherwise also
    # match nested sets such as typstPackages.heroic.
    return {attr: p for attr, p in packages.items() if "." not in attr}


def platforms(pkgs):
    declared = [p["meta"]["platforms"] for p in pkgs if p["meta"].get("platforms")]
    if not declared:
        return None  # nixpkgs puts no restriction on where it can be built
    systems = [s for ps in declared for s in ps if isinstance(s, str)]
    return {
        "linux": any(s.endswith("-linux") for s in systems),
        "darwin": any(s.endswith("-darwin") for s in systems),
    }


def repology_get(path):
    """GET a Repology path, trying each domain. Returns (json, final_url), or
    (None, None) on 404."""
    last_err = None
    for base in BASE_URLS:
        req = urllib.request.Request(base + path, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode()), resp.geturl()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, None
            last_err = e
        except (urllib.error.URLError, OSError) as e:
            print(f"  {base} unreachable ({e}), trying next domain...", file=sys.stderr)
            last_err = e
    raise last_err


def project_for_attr(attr):
    """Resolve a nixpkgs attribute to its Repology project. Returns
    (project, entries), or (None, None) if Repology doesn't know it."""
    query = urllib.parse.urlencode({
        "repo": NIX_REPO, "name_type": "srcname",
        "target_page": "api_v1_project", "name": attr,
    })
    entries, url = repology_get(f"/tools/project-by?{query}")
    if entries is None:
        return None, None
    return urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]), entries


def project_by_name(name):
    entries, _ = repology_get(f"/api/v1/project/{urllib.parse.quote(name)}")
    # Repology answers an unknown project with an empty list, not a 404.
    return (name, entries) if entries else (None, None)


def project_rows(proj, nixpkgs):
    """Index rows for one Repology project: normally one, but one per version
    when the tracked nixpkgs variants differ (wesnoth / wesnoth-devel).
    Variants sharing a version (heroic / heroic-unwrapped) stay one row."""
    entries = proj["entries"]
    nix_all = [e for e in entries if e.get("repo") == NIX_REPO]
    others = [e for e in entries if e.get("repo") != NIX_REPO]

    groups = {}  # version -> nix entries of tracked attrs
    for e in nix_all:
        if e.get("srcname") in proj["attrs"]:
            groups.setdefault(e.get("version"), []).append(e)
    if len(groups) < 2:
        nix = next(iter(groups.values()), nix_all)[:1]
        return [make_row(proj, proj["name"], proj["attrs"], nix[0] if nix else None, others, nixpkgs, devel=False)]

    # Stable first: the variant Repology calls newest, else the shortest attr
    # (wesnoth before wesnoth-devel). The rest compare against devel versions.
    ordered = sorted(groups.values(), key=lambda g: (
        not any(e.get("status") == "newest" for e in g),
        min(len(e["srcname"]) for e in g),
        min(e["srcname"] for e in g),
    ))
    rows, used = [], set()
    for i, group in enumerate(ordered):
        attrs = sorted(e["srcname"] for e in group)
        pname = nixpkgs[attrs[0]].get("pname") if attrs[0] in nixpkgs else None
        # Variants can share a pname (_1password-gui / -beta): fall back to the attr.
        name = pname if pname and pname not in used else attrs[0]
        used.add(name)
        rows.append(make_row(proj, name, attrs, group[0], others, nixpkgs, devel=i > 0))
    return rows


def make_row(proj, name, attrs, nix, others, nixpkgs, devel):
    newest = lambda status: next((e.get("version") for e in others if e.get("status") == status), None)
    row = {
        "name": name,
        "project": proj["project"],
        "attrs": attrs,
        "nixVersion": nix.get("version") if nix else None,
        "nixStatus": nix.get("status") if nix else "missing",
        "nixVulnerable": bool(nix.get("vulnerable")) if nix else False,
        "refVersion": (devel and newest("devel")) or newest("newest"),
        "repoCount": len(others),
        # A devel variant of a split project, or a version Repology itself
        # classifies as devel (lincity).
        "devel": devel or (nix or {}).get("status") == "devel",
    }
    pkgs = [nixpkgs[a] for a in attrs if a in nixpkgs]
    if pkgs:  # not in nixpkgs: nothing to say about platforms or homepage
        row["platforms"] = platforms(pkgs)
        homepage = next((p["meta"].get("homepage") for p in pkgs if p["meta"].get("homepage")), None)
        row["homepage"] = homepage[0] if isinstance(homepage, list) else homepage
    return row


def main():
    shutil.rmtree(TMP_DIR, ignore_errors=True)  # leftover from a failed run
    os.makedirs(TMP_DIR)

    lists = read_lists()
    nixpkgs = load_nixpkgs_index()

    # pname -> nixpkgs attributes to look up (empty if nixpkgs lacks it)
    wanted = {}
    handles = {h.lower() for h in lists["maintainers"]}
    for attr, p in sorted(nixpkgs.items()):
        if any(isinstance(m, dict) and (m.get("github") or "").lower() in handles
               for m in p["meta"].get("maintainers") or []):
            wanted.setdefault(p.get("pname") or attr, []).append(attr)
    by_pname = {}
    for attr, p in nixpkgs.items():
        by_pname.setdefault(p.get("pname"), []).append(attr)
    for pname in lists["extraPackages"]:
        wanted.setdefault(pname, sorted(by_pname.get(pname, [])))

    # Several attrs (wesnoth / wesnoth-devel, heroic / heroic-unwrapped) can
    # map to one Repology project; they're fetched once and split into rows
    # below.
    projects = {}  # project -> {"name", "project", "attrs", "entries"}
    for pname, attrs in sorted(wanted.items()):
        print(f"Resolving {pname}...", file=sys.stderr)
        project, entries = None, None
        for attr in attrs:
            project, entries = project_for_attr(attr)
            time.sleep(1)  # be polite to Repology's API
            if project:
                break
        if not project:
            # Not in nixpkgs, or Repology hasn't caught up yet: try the pname
            # as a Repology project name directly.
            project, entries = project_by_name(pname)
            time.sleep(1)

        key = project or pname
        if key in projects:
            projects[key]["attrs"] += attrs
            continue
        with open(os.path.join(TMP_DIR, f"{key}.json"), "w") as f:
            json.dump(entries or [], f, indent=2, sort_keys=True)
        projects[key] = {"name": pname, "project": project, "attrs": attrs, "entries": entries or []}

    rows = [row for proj in projects.values() for row in project_rows(proj, nixpkgs)]
    with open(os.path.join(TMP_DIR, "index.json"), "w") as f:
        json.dump({
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "packages": sorted(rows, key=lambda p: p["name"].lower()),
        }, f, indent=2, sort_keys=True)

    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.rename(TMP_DIR, OUT_DIR)


if __name__ == "__main__":
    main()
