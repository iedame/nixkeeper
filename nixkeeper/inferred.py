"""Update checks worked out from nixpkgs itself: a package fetched from a
GitHub tag (fetchFromGitHub, a release download) is checked against that
repository's tags, with the tag scheme its own tag shows ("v" + version,
...). They run with the other update checks (upstream.py), for packages
without a rule of their own or the community's (which win), unless the
lists turn them off (`workedOutChecks = false;`). Each daily sync also logs
how they compare with Repology, and with the packages' rules."""

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


def enabled(lists):
    """Whether the lists use worked-out checks: unless they turn them off with
    `workedOutChecks = false;`."""
    return (lists or {}).get("workedOutChecks") is not False


class WorkedOut:
    """The checks worked out for a sync's rows ({name: check}), why the rest
    have none (a Counter), and each row's newest version by Repology before
    the update checks change it ({name: refVersion}), to compare with."""

    def __init__(self, checks, not_worked, repology):
        self.checks, self.not_worked, self.repology = checks, not_worked, repology

    def to_run(self, rules):
        """The worked-out checks to run: those of packages without a rule."""
        return {n: c for n, c in self.checks.items() if n not in rules}


def work_out(lists, rows, rules, revision):
    """WorkedOut for rows, or None (says why): turned off, no GitHub token to
    run them with, or nixpkgs didn't evaluate. rules: the update checks the
    lists and the community give."""
    if not enabled(lists):
        return None
    if not github.token():
        print("Worked-out update checks: skipped (no GITHUB_TOKEN)", file=sys.stderr)
        return None
    rows = [row for row in rows if row.get("nixVersion")]
    try:
        attrs = {a for row in rows for a in row.get("attrs") or [row["name"]]}
        sources = nixpkgs_source.sources(attrs, revision)
    except nixpkgs_source.EvalError as e:
        print(f"Worked-out update checks: skipped ({e})", file=sys.stderr)
        return None
    checks, not_worked = {}, collections.Counter()
    for row in rows:
        if "follows" in rules.get(row["name"], {}):
            continue
        check, why = for_row(row, sources)
        if check:
            checks[row["name"]] = check
        else:
            not_worked[why] += 1
    repology = {row["name"]: row.get("refVersion") for row in rows}
    return WorkedOut(checks, not_worked, repology)


def report(worked, rows, rules, failed):
    """Log how the worked-out checks compare (a log group in the sync's
    output): those that ran, from their rows (after upstream.add_checks;
    failed: its {name: why} for them) against Repology; those of packages
    with a rule, asked here (only for this) against the rule's result."""
    by_name = {row["name"]: row for row in rows}
    failed, found = dict(failed), {}
    for name in worked.to_run(rules):
        up = by_name[name].get("upstream") or {}
        if up.get("inferred"):
            found[name] = up["version"]

    def keep_previous(name, why):
        failed[name] = why

    def add(name, version, where, what, **_):
        if version is None:
            failed[name] = f"nothing in {where} matches {what}"
        else:
            found[name] = version

    ruled = {n: c for n, c in worked.checks.items() if n in rules}
    if ruled:
        # The same requests as the tags checks: GITHUB_REPOS_BATCH
        # repositories each.
        upstream.check_tags(github.token(), ruled, keep_previous, add)
    lines = collections.defaultdict(list)
    for name in sorted(found):
        # Repology's view as it was before the update checks.
        row = {**by_name[name], "refVersion": worked.repology.get(name)}
        kind, what = verdict(row, found[name], name in rules)
        lines[kind].append(
            f"  {name} {row['nixVersion']}: {what}  ({worked.checks[name]['github']})"
        )
    agree, disagree = len(lines["agree"]), len(lines["disagree"])
    used = len(worked.to_run(rules))
    print(
        f"::group::Worked-out update checks: {len(worked.checks)} of "
        f"{len(worked.repology)} packages ({used} used, {len(ruled)} with a "
        f"rule), {agree} agree with Repology or their rule, {disagree} don't, "
        f"{len(failed)} failed",
        file=sys.stderr,
    )
    print(
        "Not worked out: "
        + ", ".join(f"{n} {why}" for why, n in worked.not_worked.most_common()),
        file=sys.stderr,
    )
    for title, kind in (("Disagree", "disagree"), ("Agree", "agree")):
        print(f"{title}:", *lines[kind], sep="\n", file=sys.stderr)
    print("Failed (left to Repology):", file=sys.stderr)
    for name in sorted(failed):
        print(f"  {name}: {failed[name]}", file=sys.stderr)
    print("::endgroup::", file=sys.stderr)
