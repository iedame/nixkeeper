#!/usr/bin/env python3
"""Fetch Repology status for every package tracked in package-lists/.

The tracked set is every nixpkgs package whose meta.maintainers includes one
of the GitHub handles in package-lists/default.nix, plus every entry from the
lists it imports (an attribute name, or a pname). Each is looked up on
Repology via its nixpkgs attribute name.

Writes one raw JSON file per Repology project to data/<project>.json, plus a
data/index.json summary focused on the nix_unstable status of each.
"""
import json
import os
import re
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
# Repology statuses the page shows as outdated ("legacy": outdated while the
# same repo has a newer version in another package).
OUTDATED_STATUSES = {"outdated", "legacy"}
GITHUB_REPO = "NixOS/nixpkgs"
GITHUB_SEARCH_BATCH = 20  # searches per GraphQL request
# nixpkgs PR/issue titles name packages in versioned sets by their alias
# ("python3Packages.requests: 2.34 -> 2.35"), which the index doesn't carry.
SEARCH_ALIASES = [
    (re.compile(r"^python3\d+Packages\."), "python3Packages."),
]


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
        # Includes nested sets (haskellPackages.foo), but not aliases such as
        # python3Packages: those need their versioned name (python313Packages).
        return json.loads(brotli.decompress(resp.read()))["packages"]


def data_file(key):
    """File name for a project's raw data: Repology names like python:requests
    contain characters that don't belong in file names or URLs."""
    return re.sub(r"[^A-Za-z0-9._+-]", "_", key) + ".json"


def search_term(attr):
    for pattern, alias in SEARCH_ALIASES:
        attr = pattern.sub(alias, attr)
    return attr


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


def resolve(fallback, attrs):
    """Find the Repology project for tracked nixpkgs attrs, else for fallback
    as a project name. Returns (project, entries), (None, None) if Repology
    doesn't know it; raises on failure."""
    for attr in attrs:
        project, entries = project_for_attr(attr)
        time.sleep(1)  # be polite to Repology's API
        if project:
            return project, entries
    # Not in nixpkgs, or Repology hasn't caught up yet: try the fallback as a
    # Repology project name directly.
    project, entries = project_by_name(fallback)
    time.sleep(1)
    return project, entries


def load_previous_run(out_dir=OUT_DIR):
    """The last successful run's index, or an empty one."""
    try:
        with open(os.path.join(out_dir, "index.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"packages": []}


def previous_project(previous, pname, attrs, out_dir=OUT_DIR):
    """Reuse the last run's data for a pname whose lookup failed. Returns
    (project, entries, stale_since), or None if there's nothing to reuse."""
    for row in previous["packages"]:
        if pname in (row.get("searchTerm"), row["name"]) or set(attrs) & set(row.get("attrs") or []):
            entries = []
            if row.get("project"):
                try:
                    with open(os.path.join(out_dir, row.get("dataFile") or f"{row['project']}.json")) as f:
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
        attrs = sorted(proj["attrs"])
        # Named after its nixpkgs attribute, like the lists and GitHub searches;
        # the list entry itself when nixpkgs doesn't have it.
        name = attrs[0] if attrs else proj["name"]
        return [make_row(proj, name, attrs, nix[0] if nix else None, others, nixpkgs, devel=False)]

    # Stable first: the variant Repology calls newest, else the shortest attr
    # (wesnoth before wesnoth-devel). The rest compare against devel versions.
    ordered = sorted(groups.values(), key=lambda g: (
        not any(e.get("status") == "newest" for e in g),
        min(len(e["srcname"]) for e in g),
        min(e["srcname"] for e in g),
    ))
    rows = []
    for i, group in enumerate(ordered):
        attrs = sorted(e["srcname"] for e in group)
        rows.append(make_row(proj, attrs[0], attrs, group[0], others, nixpkgs, devel=i > 0))
    return rows


def make_row(proj, name, attrs, nix, others, nixpkgs, devel):
    newest = lambda status: next((e.get("version") for e in others if e.get("status") == status), None)
    row = {
        "name": name,
        # What the GitHub PR/issue searches use: the attribute name, which
        # unlike the pname tells variants apart (_1password-gui and
        # _1password-gui-beta are both pname "1password").
        "searchTerm": search_term(attrs[0]) if attrs else name,
        "project": proj["project"],
        "dataFile": proj["dataFile"],
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


def github_search_counts(token, queries):
    """Run several GitHub issue/PR searches in one GraphQL request and return
    their result counts, in order. A search GitHub couldn't answer gives None;
    a failed request gives all None."""
    params = ", ".join(f"$q{i}: String!" for i in range(len(queries)))
    fields = "\n".join(f"  s{i}: search(type: ISSUE, first: 0, query: $q{i}) {{ issueCount }}" for i in range(len(queries)))
    body = json.dumps({
        "query": f"query({params}) {{\n{fields}\n}}",
        "variables": {f"q{i}": q for i, q in enumerate(queries)},
    }).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"  GitHub search batch failed ({e})", file=sys.stderr)
        return [None] * len(queries)
    for err in result.get("errors") or []:
        print(f"  GitHub search error: {err.get('message')}", file=sys.stderr)
    data = result.get("data") or {}
    return [(data.get(f"s{i}") or {}).get("issueCount") for i in range(len(queries))]


def add_github_counts(rows):
    """Open nixpkgs PRs and issues with each row's attribute name in the title: the same
    searches the page links to. Title-only because nixpkgs titles name the
    package, while bodies of big rebuild PRs list hundreds of unrelated ones."""
    token = github_token()
    if not token:
        print("No GITHUB_TOKEN or gh login: skipping open PR/issue counts.", file=sys.stderr)
        return
    searches = [
        (row, field, f"repo:{GITHUB_REPO} is:{kind} state:open in:title {row['searchTerm']}")
        for row in rows
        for kind, field in (("pr", "openPRs"), ("issue", "openIssues"))
    ]
    print(f"Counting open PRs/issues ({len(searches)} searches)...", file=sys.stderr)
    for start in range(0, len(searches), GITHUB_SEARCH_BATCH):
        batch = searches[start:start + GITHUB_SEARCH_BATCH]
        counts = github_search_counts(token, [q for _, _, q in batch])
        for (row, field, _), count in zip(batch, counts):
            row[field] = count


def tracked_packages(lists, nixpkgs):
    """What to track, from the package lists and the nixpkgs index: name ->
    (nixpkgs attrs to look up, Repology project name to try if none of them
    resolve). Maintained packages go one attr at a time: with nested sets a
    pname can mean unrelated packages (foo, python313Packages.foo)."""
    wanted = {}
    handles = {h.lower() for h in lists["maintainers"]}
    for attr, p in sorted(nixpkgs.items()):
        if any(isinstance(m, dict) and (m.get("github") or "").lower() in handles
               for m in p["meta"].get("maintainers") or []):
            wanted[attr] = ([attr], p.get("pname") or attr)
    # Bare pnames only match top-level packages: "heroic" shouldn't pull in
    # typstPackages.heroic.
    by_pname = {}
    for attr, p in nixpkgs.items():
        if "." not in attr:
            by_pname.setdefault(p.get("pname"), []).append(attr)
    for name in lists["extraPackages"]:
        # An exact attribute name tracks just that package (_1password-gui
        # without its -beta, which shares the pname "1password").
        attrs = [name] if name in nixpkgs else sorted(by_pname.get(name, []))
        if not attrs:
            print(f"  {name} is neither a nixpkgs attribute nor a top-level pname "
                  "(aliases like python3Packages need their versioned name)", file=sys.stderr)
        wanted.setdefault(name, (attrs, name))
    return wanted


def collect_projects(wanted, previous, resolve=resolve, out_dir=OUT_DIR):
    """Look up every tracked package on Repology, falling back to the previous
    run's data (in out_dir) when a lookup fails. Several attrs (wesnoth /
    wesnoth-devel, heroic / heroic-unwrapped) can map to one project; those
    are merged here and split into rows by project_rows. Returns project ->
    {"name", "project", "attrs", "entries", "dataFile"[, "staleSince"]}, or
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
            reused = previous_project(previous, pname, attrs, out_dir)
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

    if len(failed) > MAX_FAILED_SHARE * len(wanted):
        sys.exit(f"Repology lookups failed for {len(failed)} of {len(wanted)} packages; "
                 f"keeping the previous data. Failed: {', '.join(failed)}")
    return projects


def build_rows(projects, nixpkgs):
    """All index rows, sorted by name."""
    rows = []
    for proj in projects.values():
        for row in project_rows(proj, nixpkgs):
            if proj.get("staleSince"):
                row["staleSince"] = proj["staleSince"]  # when its data was last fetched
            rows.append(row)
    return sorted(rows, key=lambda p: p["name"].lower())


def add_outdated_since(rows, previous, now):
    """Mark when each outdated row first became outdated. Neither Repology nor
    nixpkgs has that date, so it's carried from run to run: kept while the row
    stays outdated (even if nixpkgs updates but is still behind), set to now
    when it newly falls behind, dropped once it's caught up."""
    before = {row["name"]: row for row in previous["packages"]}
    for row in rows:
        if row["nixStatus"] in OUTDATED_STATUSES:
            row["outdatedSince"] = before.get(row["name"], {}).get("outdatedSince") or now


def main():
    shutil.rmtree(TMP_DIR, ignore_errors=True)  # leftover from a failed run
    os.makedirs(TMP_DIR)

    now = datetime.now(timezone.utc).isoformat()
    nixpkgs = load_nixpkgs_index()
    wanted = tracked_packages(read_lists(), nixpkgs)
    previous = load_previous_run()
    projects = collect_projects(wanted, previous)
    for proj in projects.values():
        with open(os.path.join(TMP_DIR, proj["dataFile"]), "w") as f:
            json.dump(proj["entries"], f, indent=2, sort_keys=True)

    rows = build_rows(projects, nixpkgs)
    add_outdated_since(rows, previous, now)
    add_github_counts(rows)
    with open(os.path.join(TMP_DIR, "index.json"), "w") as f:
        json.dump({
            "checkedAt": now,
            "packages": rows,
        }, f, indent=2, sort_keys=True)

    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.rename(TMP_DIR, OUT_DIR)


if __name__ == "__main__":
    main()
