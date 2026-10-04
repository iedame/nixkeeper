"""Update checks worked out from nixpkgs itself, side by side with Repology:
a package fetched from a GitHub tag (fetchFromGitHub, a release download)
is checked against that repository's tags, with the tag scheme its own tag
shows ("v" + version, ...). Not used for the data yet: each daily sync logs
where these and Repology disagree, so they can be judged before anyone relies
on them."""

import collections
import re
import sys

from .sources import github, upstream
from .sources import nixpkgs as nixpkgs_source
from .versions import is_newer

GITHUB = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/|$)")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
RELEASE = re.compile(r"/releases/download/([^/]+)/")
ARCHIVE = re.compile(r"/archive/(?:refs/tags/)?(.+?)\.(?:tar\.gz|zip)$")
# Versions made of numbers only (1.19.28, 2024.05, 7_2): the tags a check
# worked out this way looks for. Others (betas, unstable versions) are left
# to Repology for now.
PLAIN = re.compile(r"[0-9]+(?:[._-][0-9]+)*")


def tag_of(src):
    """The tag (or commit) src was fetched from, or None."""
    if src.get("tag"):
        return src["tag"]
    rev = src.get("rev") or ""
    if rev.startswith("refs/tags/"):
        return rev.removeprefix("refs/tags/")
    url = src.get("url") or ""
    if m := RELEASE.search(url) or ARCHIVE.search(url):
        return m.group(1)
    return rev or None


def github_check(src):
    """(check, None): the GitHub tags check src's package would have, as an
    update check ({"github", "tags"}); or (None, why not)."""
    m = GITHUB.match(src.get("gitRepoUrl") or "") or GITHUB.match(src.get("url") or "")
    if not m:
        return None, "not from GitHub"
    version, tag = src.get("version") or "", tag_of(src)
    if not tag:
        return None, "no tag"
    if COMMIT.match(tag):
        return None, "a commit (unstable version)"
    if not PLAIN.fullmatch(version):
        return None, "not a plain version"
    if not tag.endswith(version):
        return None, "tag doesn't end with the version"
    # The separators the version uses (dots, as a rule), so 1.2.3 doesn't
    # match 1_2_3-style tags of another scheme.
    seps = "".join(sorted(set(re.sub("[0-9]", "", version)))) or "."
    number = f"[0-9]+(?:[{re.escape(seps)}][0-9]+)*"
    prefix = re.escape(tag.removesuffix(version))
    return {
        "github": f"{m.group(1)}/{m.group(2)}",
        "tags": f"^{prefix}({number})$",
    }, None


def for_row(row, sources):
    """(check, None) from the first of row's attributes that gives one, or
    (None, why not) from the first that has a source."""
    why = "no source"
    for attr in row.get("attrs") or [row["name"]]:
        if attr not in sources:
            continue
        check, reason = github_check(sources[attr])
        if check:
            return check, None
        if why == "no source":
            why = reason
    return None, why


def verdict(row, version, rule):
    """How a worked-out check's version compares with what the sync has:
    ("agree" or "disagree", what to say). rule: the row's own update check,
    when it has one: it's compared with that instead of Repology."""
    nix = row.get("nixVersion")
    if rule:
        theirs = (row.get("upstream") or {}).get("version")
        if theirs is None or theirs == version:
            return "agree", f"{version}, as its rule"
        return "disagree", f"{version}, its rule {theirs}"
    by_github = is_newer(version, nix)
    by_repology = row.get("nixStatus") in ("outdated", "legacy")
    ref = row.get("refVersion")
    if not by_github and not by_repology:
        return "agree", "up to date"
    if by_github and by_repology:
        if ref == version:
            return "agree", f"outdated, {version}"
        return "disagree", f"both outdated: GitHub {version}, Repology {ref}"
    if by_github:
        return "disagree", f"GitHub {version}, Repology up to date"
    return "disagree", f"Repology {ref}, GitHub {version}"


def compare(rows, checks, revision):
    """Work out the checks for rows, ask GitHub, and log how they compare
    (a log group in the sync's output). checks: the update checks the lists
    and community rules give (own rules are compared with too). Changes no
    row; anything that fails only skips this."""
    token = github.token()
    if not token:
        print("Worked-out update checks: skipped (no GITHUB_TOKEN)", file=sys.stderr)
        return
    rows = [row for row in rows if row.get("nixVersion")]
    try:
        attrs = {a for row in rows for a in row.get("attrs") or [row["name"]]}
        sources = nixpkgs_source.sources(attrs, revision)
    except nixpkgs_source.EvalError as e:
        print(f"Worked-out update checks: skipped ({e})", file=sys.stderr)
        return
    worked, not_worked = {}, collections.Counter()
    for row in rows:
        if "follows" in checks.get(row["name"], {}):
            continue
        check, why = for_row(row, sources)
        if check:
            worked[row["name"]] = check
        else:
            not_worked[why] += 1
    failed, found = {}, {}

    def keep_previous(name, why):
        failed[name] = why

    def add(name, version, where, what, **_):
        if version is None:
            failed[name] = f"nothing in {where} matches {what}"
        else:
            found[name] = version

    # The same requests as the tags checks: GITHUB_REPOS_BATCH repositories
    # each.
    upstream.check_tags(token, worked, keep_previous, add)
    by_name = {row["name"]: row for row in rows}
    lines = collections.defaultdict(list)
    for name in sorted(found):
        row = by_name[name]
        kind, what = verdict(row, found[name], name in checks)
        lines[kind].append(
            f"  {name} {row['nixVersion']}: {what}  ({worked[name]['github']})"
        )
    agree, disagree = len(lines["agree"]), len(lines["disagree"])
    print(
        f"::group::Worked-out update checks (not used yet): {len(worked)} of "
        f"{len(rows)} packages, {agree} agree with Repology or their rule, "
        f"{disagree} don't, {len(failed)} failed",
        file=sys.stderr,
    )
    print(
        "Not worked out: "
        + ", ".join(f"{n} {why}" for why, n in not_worked.most_common()),
        file=sys.stderr,
    )
    for title, kind in (("Disagree", "disagree"), ("Agree", "agree")):
        print(f"{title}:", *lines[kind], sep="\n", file=sys.stderr)
    print("Failed:", file=sys.stderr)
    for name in sorted(failed):
        print(f"  {name}: {failed[name]}", file=sys.stderr)
    print("::endgroup::", file=sys.stderr)
