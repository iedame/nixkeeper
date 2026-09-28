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
RETRY_DELAYS = [5, 15]  # seconds before each retry of a failed Repology request
# If more lookups than this fail, Repology is likely down: abort and keep the
# previous data (the page flags it as stale) instead of publishing a run that's
# mostly "not refreshed".
MAX_FAILED_SHARE = 0.5
GITHUB_REPO = "NixOS/nixpkgs"


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
    """GET a Repology path, trying each domain, and retrying the lot after
    RETRY_DELAYS seconds. Returns (json, final_url), or (None, None) on 404."""
    last_err = None
    for delay in [0, *RETRY_DELAYS]:
        if delay:
            print(f"  retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)
        for base in BASE_URLS:
            req = urllib.request.Request(base + path, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode()), resp.geturl()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None, None
                print(f"  {base} answered {e.code}", file=sys.stderr)
                last_err = e
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f"  {base} failed ({e}), trying next domain...", file=sys.stderr)
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


def resolve(pname, attrs):
    """Find the Repology project for a tracked pname. Returns (project,
    entries), (None, None) if Repology doesn't know it; raises on failure."""
    for attr in attrs:
        project, entries = project_for_attr(attr)
        time.sleep(1)  # be polite to Repology's API
        if project:
            return project, entries
    # Not in nixpkgs, or Repology hasn't caught up yet: try the pname as a
    # Repology project name directly.
    project, entries = project_by_name(pname)
    time.sleep(1)
    return project, entries


def load_previous_run():
    """The last successful run's index, or an empty one."""
    try:
        with open(os.path.join(OUT_DIR, "index.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"packages": []}


def previous_project(previous, pname, attrs):
    """Reuse the last run's data for a pname whose lookup failed. Returns
    (project, entries, stale_since), or None if there's nothing to reuse."""
    for row in previous["packages"]:
        if pname in (row.get("pname"), row["name"]) or set(attrs) & set(row.get("attrs") or []):
            entries = []
            if row.get("project"):
                try:
                    with open(os.path.join(OUT_DIR, f"{row['project']}.json")) as f:
                        entries = json.load(f)
                except (OSError, ValueError):
                    return None
            return row.get("project"), entries, row.get("staleSince") or previous.get("checkedAt")
    return None


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
        # What the page's GitHub PR/issue searches use. Differs from name
        # when split variants share a pname (_1password-gui-beta -> 1password).
        "pname": (nixpkgs[attrs[0]].get("pname") if attrs and attrs[0] in nixpkgs else None) or name,
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


def github_token():
    """GITHUB_TOKEN (set by the workflow), else the local gh login, else None."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        return result.stdout.strip() or None
    except FileNotFoundError:
        return None


def github_open_count(token, kind, term):
    """Number of open nixpkgs PRs or issues (kind "pr" / "issue") with term in
    the title: the same search the page links to. Title-only because nixpkgs
    titles name the package, while bodies of big rebuild PRs list hundreds of
    unrelated ones. None if the search failed."""
    query = urllib.parse.urlencode({"q": f"repo:{GITHUB_REPO} is:{kind} state:open in:title {term}", "per_page": 1})
    req = urllib.request.Request(f"https://api.github.com/search/issues?{query}", headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())["total_count"]
    except (urllib.error.URLError, OSError, KeyError) as e:
        # e.g. rate limited: leave this count blank rather than fail the run
        print(f"  GitHub search for {kind} {term!r} failed ({e})", file=sys.stderr)
        return None


def add_github_counts(rows):
    token = github_token()
    if not token:
        print("No GITHUB_TOKEN or gh login: skipping open PR/issue counts.", file=sys.stderr)
        return
    for row in rows:
        print(f"Counting open PRs/issues for {row['pname']}...", file=sys.stderr)
        for kind, field in (("pr", "openPRs"), ("issue", "openIssues")):
            row[field] = github_open_count(token, kind, row["pname"])
            time.sleep(2.1)  # search API allows 30 requests/minute


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
    previous = load_previous_run()
    projects = {}  # project -> {"name", "project", "attrs", "entries"[, "staleSince"]}
    failed = []
    for pname, attrs in sorted(wanted.items()):
        print(f"Resolving {pname}...", file=sys.stderr)
        stale_since = None
        try:
            project, entries = resolve(pname, attrs)
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(pname)
            reused = previous_project(previous, pname, attrs)
            if not reused:
                print(f"  giving up on {pname} ({e}); no previous data, skipping it this run", file=sys.stderr)
                continue
            project, entries, stale_since = reused
            print(f"  giving up on {pname} ({e}); reusing data from {stale_since}", file=sys.stderr)

        key = project or pname
        if key in projects:
            projects[key]["attrs"] += attrs
            continue
        with open(os.path.join(TMP_DIR, f"{key}.json"), "w") as f:
            json.dump(entries or [], f, indent=2, sort_keys=True)
        projects[key] = {"name": pname, "project": project, "attrs": attrs, "entries": entries or []}
        if stale_since:
            projects[key]["staleSince"] = stale_since

    if len(failed) > MAX_FAILED_SHARE * len(wanted):
        sys.exit(f"Repology lookups failed for {len(failed)} of {len(wanted)} packages; "
                 f"keeping the previous data. Failed: {', '.join(failed)}")

    rows = []
    for proj in projects.values():
        for row in project_rows(proj, nixpkgs):
            if proj.get("staleSince"):
                row["staleSince"] = proj["staleSince"]  # when its data was last fetched
            rows.append(row)
    add_github_counts(rows)
    with open(os.path.join(TMP_DIR, "index.json"), "w") as f:
        json.dump({
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "packages": sorted(rows, key=lambda p: p["name"].lower()),
        }, f, indent=2, sort_keys=True)

    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.rename(TMP_DIR, OUT_DIR)


if __name__ == "__main__":
    main()
