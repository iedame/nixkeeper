"""nixkeeper's own update checks (package-lists/update-checks.nix): the newest
upstream release of a package, from its GitHub repository's tags or from a web
page such as the vendor's release notes, or for an unstable version
("1.0-unstable-2024-05-01"), the commits on the branch it follows. A version
only counts as newest on Repology once repositories it trusts package it (the
AUR alone doesn't), so without this a fresh release leaves nixpkgs looking up
to date."""

import re
import sys
import urllib.error
import urllib.parse
from datetime import UTC, datetime, timedelta

from .. import community as community_rules
from .. import history
from ..versions import is_newer, version_key
from . import github, http

__all__ = ["is_newer", "version_key"]  # also used from here (and the tests)


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


# nixpkgs' unstable versions: what they're based on, then the date (UTC) of
# the commit they package, e.g. "5.1.0-b2-unstable-2022-11-14".
UNSTABLE = re.compile(r"^(.*-unstable-)([0-9]{4}-[0-9]{2}-[0-9]{2})$")

# When newer commits make an unstable version outdated: once one of them has
# waited this many days, or there are this many of them (whichever comes
# first; None: not that way). A check's outdatedAfter overrides either.
OUTDATED_AFTER = {"days": 90, "commits": None}


def unstable_date(nix_version):
    """The date in an unstable version, or None if it isn't one."""
    m = UNSTABLE.match(nix_version or "")
    return m.group(2) if m else None


def unstable_version(nix_version, committed):
    """nixpkgs' unstable version, moved to the date of the commit committed
    (GitHub's ISO time) if that's later: the version an update to that commit
    would have. None if nix_version isn't an unstable version."""
    m = UNSTABLE.match(nix_version or "")
    if not m:
        return None
    when = datetime.fromisoformat(committed.replace("Z", "+00:00"))
    date = when.astimezone(UTC).date().isoformat()
    return m.group(1) + max(date, m.group(2))


def outdated_after(check):
    """A branch check's limits: the defaults, with its own outdatedAfter."""
    return {**OUTDATED_AFTER, **(check.get("outdatedAfter") or {})}


def apply(row, found):
    """Record a check's result on its row. When upstream is ahead of nixpkgs,
    it's also the version the row is compared against (unless Repology has
    seen an even newer one). found["newer"], if given, says whether it counts
    as ahead (a branch check's newer commits may not count yet)."""
    newer = found.get("newer")
    if newer is None:
        newer = is_newer(found["version"], row.get("nixVersion"))
    found = {**found, "newer": newer}
    row["upstream"] = found
    if found["newer"] and not is_newer(row.get("refVersion") or "", found["version"]):
        row["refVersion"] = found["version"]


def add_checks(rows, checks, previous, now, community=frozenset()):
    """Run the update checks for rows that have one. A check that can't run,
    GitHub or web page alike, keeps the previous run's result and marks the
    row as not refreshed: usually the check itself needs fixing (a moved page,
    a changed tag scheme). community: the names whose check is a community
    rule (community.py), held to its limits and fetched in safe mode."""
    by_name = {row["name"]: row for row in rows}
    # Checks for untracked packages: reported with the lists (listcheck.py).
    # follows has nothing to fetch: follows.py applies it after master.
    wanted = {
        name: check
        for name, check in checks.items()
        if name in by_name and "follows" not in check
    }
    if not wanted:
        return
    print(f"Running {len(wanted)} update checks...", file=sys.stderr)
    before = {row["name"]: row for row in previous["packages"]}

    def keep_previous(name, why):
        # Said so, for the page: a community rule is fixed in nixkeeper.
        if name in community and not why.startswith("community rule"):
            why = f"community rule: {why}"
        print(f"::warning::update check for {name}: {why}", file=sys.stderr)
        old = before.get(name) or {}
        if old.get("upstream"):
            apply(by_name[name], old["upstream"])
        history.not_refreshed(by_name[name], "upstream", why, old, now)

    def found(name, version, where, what, **extra):
        if version is None:
            keep_previous(name, f"nothing in {where} matches {what}")
        else:
            if name in community:
                extra["community"] = True
            apply(by_name[name], {"version": version, "checkedAt": now, **extra})

    # A community rule beyond its limits is refused, never run.
    for name in sorted(set(wanted) & set(community)):
        if why := community_rules.safety(wanted[name]):
            keep_previous(name, f"community rule refused: {why}")
            del wanted[name]

    github_checks = {n: c for n, c in wanted.items() if "github" in c}
    if github_checks:
        versions = {n: by_name[n].get("nixVersion") for n in github_checks}
        check_github(github_checks, versions, now, keep_previous, found)
    for name, check in wanted.items():
        if "url" in check:
            last = (before.get(name) or {}).get("upstream")
            check_page(name, check, keep_previous, found, name in community, last)


def check_github(checks, versions, now, keep_previous, found):
    """All GitHub checks: tags in one request, branches in another.
    versions: nixpkgs' version of each package, which a branch check compares
    against."""
    token = github.token()
    if not token:
        for name in checks:
            keep_previous(name, "no GITHUB_TOKEN or gh login")
        return
    tag_checks = {n: c for n, c in checks.items() if "tags" in c}
    branch_checks = {n: c for n, c in checks.items() if "branch" in c}
    if tag_checks:
        check_tags(token, tag_checks, keep_previous, found)
    if branch_checks:
        check_branches(token, branch_checks, versions, now, keep_previous, found)


def check_tags(token, checks, keep_previous, found):
    """Checks against a repository's tags."""
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


def check_branches(token, checks, versions, now, keep_previous, found):
    """Checks for unstable versions, against the commits on the branch the
    package follows since the one nixpkgs has: outdated once one of them has
    waited long enough, or there are enough of them (outdated_after)."""
    queries = {}
    for name, check in checks.items():
        date = unstable_date(versions.get(name))
        if date is None:
            keep_previous(
                name,
                f"nixpkgs' version {versions.get(name)} isn't an unstable version "
                "(…-unstable-YYYY-MM-DD): use a tags or url check",
            )
            continue
        # Commits from the day after nixpkgs' (its own day is the same version).
        since = datetime.fromisoformat(date).replace(tzinfo=UTC) + timedelta(days=1)
        # Commits old enough to count: up to `days` ago.
        days = outdated_after(check)["days"]
        until = None
        if days is not None:
            until = datetime.fromisoformat(now) - timedelta(days=days)
            if until <= since:
                until = None  # none can have waited that long yet
        queries[name] = (
            check["github"],
            check["branch"],
            since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            until and until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    if not queries:
        return
    try:
        results = github.branch_commits(token, list(queries.values()))
    except (urllib.error.URLError, OSError, ValueError) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        for name in queries:
            keep_previous(name, f"GitHub request failed ({e})")
        return
    for (name, (repo, branch, _, until)), head in zip(
        queries.items(), results, strict=True
    ):
        if head is None:
            keep_previous(
                name, f"couldn't read branch {branch} of {repo} (renamed or deleted?)"
            )
            continue
        limits = outdated_after(checks[name])
        behind, waited = head["since"], head["until"] if until else 0
        found(
            name,
            unstable_version(versions[name], head["committedDate"]),
            f"branch {branch} of {repo}",
            "",
            newer=bool(
                behind
                and (
                    (limits["days"] is not None and waited > 0)
                    or (limits["commits"] is not None and behind >= limits["commits"])
                )
            ),
            behind=behind,
            outdatedAfter=limits,
            repo=repo,
            label=f"{repo} {branch} branch",
            url=f"https://github.com/{repo}/commits/{branch}",
            commit=head["oid"],
        )


def check_page(name, check, keep_previous, found, safe=False, last=None):
    """A check against a web page, e.g. a vendor's release notes. safe: a
    community rule's page (http.get's safe mode). last: the row's last
    result ("upstream"). If it read this same page with the same pattern,
    the server is asked to send it only if it changed since (http.get_page):
    if it hasn't, what was found then still holds, without downloading it
    again (the Edge check's page is 1 MB, hourly)."""
    url, pattern = check["url"], check["pattern"]
    last = last or {}
    cached = last.get("page") or {}
    if last.get("url") != url or cached.get("pattern") != pattern:
        cached = None  # read another way: nothing to compare with
    try:
        text, page = http.get_page(url, cached and last.get("version") and cached, safe)
        if text is None:
            keep_previous(name, f"{url} answered 404 (moved?)")
            return
        if text is http.NOT_MODIFIED:
            found(
                name,
                last["version"],
                url,
                pattern,
                label=urllib.parse.urlsplit(url).netloc,
                url=url,
                page=cached,
            )
            return
        version = latest_on_page(text, pattern)
    except http.UnsafeURL as e:
        keep_previous(name, f"community rule refused: {e.reason}")
        return
    except (urllib.error.URLError, OSError) as e:
        keep_previous(name, f"couldn't fetch {url} ({e})")
        return
    except re.error as e:
        keep_previous(name, f"invalid pattern ({e})")
        return
    # What to send next time, and the pattern it goes with.
    extra = {"page": {**page, "pattern": pattern}} if page else {}
    found(
        name,
        version,
        url,
        pattern,
        label=urllib.parse.urlsplit(url).netloc,
        url=url,
        **extra,
    )
