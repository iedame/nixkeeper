"""nixkeeper's own update checks (package-lists/update-checks.nix): the newest
upstream release of a package, straight from its repository's tags. A version
only counts as newest on Repology once repositories it trusts package it (the
AUR alone doesn't), so without this a fresh release leaves nixpkgs looking up
to date."""

import re
import sys
import urllib.error

from . import github


def version_key(version):
    """Sort key for version strings: numeric parts compare as numbers
    (1.19.28 > 1.19.9), and a letter part sorts before a number (1.0rc1 <
    1.0.1)."""
    return tuple(
        (1, int(part), "") if part.isdigit() else (0, 0, part)
        for part in re.findall(r"\d+|[A-Za-z]+", version)
    )


def is_newer(version, than):
    return bool(than) and version_key(version) > version_key(than)


def latest(tags, pattern):
    """The highest version among tags matching pattern (its capture group,
    if it has one, is the version), or None if none match."""
    regex = re.compile(pattern)
    versions = [
        m.group(1) if regex.groups else m.group(0) for m in map(regex.search, tags) if m
    ]
    return max(versions, key=version_key, default=None)


def apply(row, found):
    """Record a check's result on its row. When upstream is ahead of nixpkgs,
    it's also the version the row is compared against (unless Repology has
    seen an even newer one)."""
    found = {**found, "newer": is_newer(found["version"], row.get("nixVersion"))}
    row["upstream"] = found
    if found["newer"] and not is_newer(row.get("refVersion") or "", found["version"]):
        row["refVersion"] = found["version"]


def add_checks(rows, checks, previous):
    """Run the update checks for rows that have one. A check that can't run
    keeps the previous run's result."""
    by_name = {row["name"]: row for row in rows}
    for name in sorted(set(checks) - set(by_name)):
        print(
            f"::warning::update check for {name}: not a tracked package",
            file=sys.stderr,
        )
    wanted = {name: check for name, check in checks.items() if name in by_name}
    if not wanted:
        return
    print(f"Running {len(wanted)} update checks...", file=sys.stderr)
    before = {row["name"]: row.get("upstream") for row in previous["packages"]}

    def keep_previous(name, why):
        print(f"::warning::update check for {name}: {why}", file=sys.stderr)
        if before.get(name):
            apply(by_name[name], before[name])

    token = github.token()
    if not token:
        for name in wanted:
            keep_previous(name, "no GITHUB_TOKEN or gh login")
        return
    repos = sorted({check["github"] for check in wanted.values()})
    try:
        tags = github.latest_tags(token, repos)
    except (urllib.error.URLError, OSError, ValueError) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        for name in wanted:
            keep_previous(name, f"GitHub request failed ({e})")
        return
    for name, check in wanted.items():
        repo = check["github"]
        if repo not in tags:
            keep_previous(name, f"couldn't read the tags of {repo}")
            continue
        try:
            version = latest(tags[repo], check["tags"])
        except re.error as e:
            keep_previous(name, f"invalid tags pattern ({e})")
            continue
        if version is None:
            keep_previous(name, f"no tag of {repo} matches {check['tags']}")
            continue
        apply(
            by_name[name],
            {
                "version": version,
                "repo": repo,
                "url": f"https://github.com/{repo}/tags",
            },
        )
