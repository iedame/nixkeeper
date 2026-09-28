"""nixkeeper's own update checks (package-lists/update-checks.nix): the newest
upstream release of a package, from its GitHub repository's tags or from a web
page such as the vendor's release notes. A version
only counts as newest on Repology once repositories it trusts package it (the
AUR alone doesn't), so without this a fresh release leaves nixpkgs looking up
to date."""

import re
import sys
import urllib.error
import urllib.parse

from .. import history
from . import github, http


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


def highest(matches, regex):
    """The highest version among regex matches (its capture group, if it has
    one, is the version), or None if there are none."""
    versions = [m.group(1) if regex.groups else m.group(0) for m in matches if m]
    return max(versions, key=version_key, default=None)


def latest(tags, pattern):
    """The highest version among tags matching pattern (each tag on its own,
    so ^ and $ mean the tag's start and end)."""
    regex = re.compile(pattern)
    return highest(map(regex.search, tags), regex)


def latest_on_page(text, pattern):
    """The highest version anywhere on a page (a release-notes page lists
    old versions too; which comes first doesn't matter)."""
    regex = re.compile(pattern)
    return highest(regex.finditer(text), regex)


def apply(row, found):
    """Record a check's result on its row. When upstream is ahead of nixpkgs,
    it's also the version the row is compared against (unless Repology has
    seen an even newer one)."""
    found = {**found, "newer": is_newer(found["version"], row.get("nixVersion"))}
    row["upstream"] = found
    if found["newer"] and not is_newer(row.get("refVersion") or "", found["version"]):
        row["refVersion"] = found["version"]


def add_checks(rows, checks, previous, now):
    """Run the update checks for rows that have one. A check that can't run,
    GitHub or web page alike, keeps the previous run's result and marks the
    row as not refreshed: usually the check itself needs fixing (a moved page,
    a changed tag scheme)."""
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
    before = {row["name"]: row for row in previous["packages"]}

    def keep_previous(name, why):
        print(f"::warning::update check for {name}: {why}", file=sys.stderr)
        old = before.get(name) or {}
        if old.get("upstream"):
            apply(by_name[name], old["upstream"])
        history.not_refreshed(by_name[name], "upstream", why, old, now)

    def found(name, version, where, what, **extra):
        if version is None:
            keep_previous(name, f"nothing in {where} matches {what}")
        else:
            apply(by_name[name], {"version": version, "checkedAt": now, **extra})

    github_checks = {n: c for n, c in wanted.items() if "github" in c}
    if github_checks:
        check_github(github_checks, keep_previous, found)
    for name, check in wanted.items():
        if "url" in check:
            check_page(name, check, keep_previous, found)


def check_github(checks, keep_previous, found):
    """All GitHub checks, in one request."""
    token = github.token()
    if not token:
        for name in checks:
            keep_previous(name, "no GITHUB_TOKEN or gh login")
        return
    try:
        tags = github.latest_tags(token, sorted({c["github"] for c in checks.values()}))
    except (urllib.error.URLError, OSError, ValueError) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        for name in checks:
            keep_previous(name, f"GitHub request failed ({e})")
        return
    for name, check in checks.items():
        repo = check["github"]
        if repo not in tags:
            keep_previous(
                name, f"couldn't read the tags of {repo} (renamed or deleted?)"
            )
            continue
        try:
            version = latest(tags[repo], check["tags"])
        except re.error as e:
            keep_previous(name, f"invalid tags pattern ({e})")
            continue
        found(
            name,
            version,
            f"the tags of {repo}",
            check["tags"],
            repo=repo,
            label=f"{repo} tags",
            url=f"https://github.com/{repo}/tags",
        )


def check_page(name, check, keep_previous, found):
    """A check against a web page, e.g. a vendor's release notes."""
    url = check["url"]
    try:
        text = http.get(url)
        if text is None:
            keep_previous(name, f"{url} answered 404 (moved?)")
            return
        version = latest_on_page(text, check["pattern"])
    except (urllib.error.URLError, OSError) as e:
        keep_previous(name, f"couldn't fetch {url} ({e})")
        return
    except re.error as e:
        keep_previous(name, f"invalid pattern ({e})")
        return
    found(
        name,
        version,
        url,
        check["pattern"],
        label=urllib.parse.urlsplit(url).netloc,
        url=url,
    )
