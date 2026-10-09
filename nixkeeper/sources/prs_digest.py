"""nixkeeper-prs' digest (https://github.com/iedame/nixkeeper-prs): every
open PR and issue of nixpkgs, and the PRs merged into master since the
nixos-unstable channel's commit, as its hourly workflow lists them. The
daily sync counts each package's open PRs and issues, and finds its open
and merged update PRs, in these lists (github_bulk) instead of listing
them itself.

With the lists come the digest's own findings (facts): each PR's merge-bot
eligibility, update state, whether it blocks the update bot and which PRs
duplicate it; the PRs touching a package whose build fails on Hydra; and
the issues it checked (a build failure against Hydra now, an update
request against nixpkgs' version). add_facts gives each row those of its
own package, for its panel.

Each list is used while it was made recently (PRS_DIGEST_MAX_AGE_HOURS),
and the merged PRs only when they were listed since the very channel
commit the sync reads (a newer channel would count PRs it has as not in
it yet): else the sync lists them itself, as it did before the digest."""

import json
import re
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from . import about, http

FORMAT = 1
PR_URL = "https://github.com/NixOS/nixpkgs/pull/"
ISSUE_URL = "https://github.com/NixOS/nixpkgs/issues/"
# At most so many PRs and issues of a package in its panel (the rest are a
# GitHub search away).
SHOWN = 5
# Issue checks worth showing: something to do (close it, or still failing).
BUILD_SHOWN = {"builds", "failing"}
UPDATE_SHOWN = {"done", "partly"}
# The package a PR's title names, nixpkgs' convention ("foo: drop").
TITLE_PACKAGE = re.compile(r"^([\w.+-]+):")
# A PR's kind, as the digest reads its title (nixkeeper-prs' facts.py).
KINDS = ("drop", "init", "update")
# The digest calls any "foo: drop ..." or "foo: remove ..." a drop; most
# remove something from the package ("drop unused libmatthew_java",
# "remove meta.changelog": 85 of 125 on 2026-10-09). A removal of the
# package itself says nothing more, or says so: "foo: drop", "foo: remove
# package", "foo: drop in favor of bar", "foo: drop, bar: init at 1.0",
# "fmt_9: remove version".
REMOVAL = re.compile(
    r"^[\w.+-]+: (?:drop|remove)(?:\s*$|\s*[,;(:]|\s+(?:the\s+)?package\b"
    r"|\s+in\s+favou?r\b|\s+(?:as|since|because|due)\b|\s+version\b)",
    re.IGNORECASE,
)
# Titles name Python packages by their alias; rows by the versioned set.
PYTHON_ALIAS = ("python3packages.", "python313packages.")


def package_key(name):
    """A package's name as facts are kept by: lower case, Python's alias as
    the versioned set it points to."""
    key = (name or "").lower()
    if key.startswith(PYTHON_ALIAS[0]):
        key = PYTHON_ALIAS[1] + key[len(PYTHON_ALIAS[0]) :]
    return key


def pr_facts(pr, duplicates):
    """What the digest found of a PR, as a row's update PR keeps it:
    "mergeBot" ("ready": CI green and no conflict, else "eligible"),
    "state" (superseded, overtaken, downgrade...) with nixpkgs' version
    ("now"), "blocksBot" (the day the bot is expected to try, or True), and
    "duplicates" (the PRs it duplicates). {} when none."""
    found = {}
    if mb := pr.get("mergeBot"):
        ready = mb.get("ready") and pr.get("mergeable") != "CONFLICTING"
        found["mergeBot"] = "ready" if ready else "eligible"
    if state := pr.get("state"):
        found["state"] = state
        if now := (pr.get("update") or {}).get("now"):
            found["now"] = now
    if blocking := pr.get("blocksBot"):
        found["blocksBot"] = blocking.get("by") or True
    if others := duplicates.get(pr["n"]):
        found["duplicates"] = others[:SHOWN]
    return found


def facts(prs, groups, issues):
    """The digest's findings, by PR number and by package (package_key):
    {"prs": {number: pr_facts}, "fixes": {package: [PRs touching it while
    its build fails on Hydra]}, "issues": {package: [checked issues]},
    "open": {package: [its open PRs, not drafts: by the package its title
    names or the pkgs/by-name directories it touches]}}."""
    duplicates = {}
    for group in groups:
        for n in group.get("prs") or []:
            others = [m for m in group["prs"] if m != n]
            duplicates.setdefault(n, [])
            duplicates[n] += [m for m in others if m not in duplicates[n]]
    by_number, fixes, open_prs = {}, {}, {}
    for pr in prs:
        if found := pr_facts(pr, duplicates):
            by_number[pr["n"]] = found
        if pr.get("draft"):
            continue
        item = {"number": pr["n"], "title": pr["title"]}
        kind = next((k for k in KINDS if k in (pr.get("buckets") or [])), None)
        if kind == "drop" and not REMOVAL.match(pr["title"]):
            kind = None  # removes something from it, not the package
        if kind:
            item["kind"] = kind
        if mb := found.get("mergeBot"):
            item["mergeBot"] = mb
        named = TITLE_PACKAGE.match(pr["title"])
        title_key = package_key(named.group(1)) if named else None
        keys = {package_key(p) for p in pr.get("packages") or []} | {title_key}
        # Only the package its title names is removed: the others it touches
        # move off it (fmt_11: remove version, imhex's package.nix to fmt).
        touched = {k: v for k, v in item.items() if k != "kind"}
        for key in keys - {None}:
            mine = item if key == title_key or kind != "drop" else touched
            open_prs.setdefault(key, []).append(mine)
        for package in pr.get("hydraFailing") or {}:
            fixes.setdefault(package_key(package), []).append(
                {"number": pr["n"], "title": pr["title"], "url": PR_URL + str(pr["n"])}
            )
    checked = {}
    for issue in issues:
        hydra, update = issue.get("hydra") or {}, issue.get("update") or {}
        if hydra.get("verdict") in BUILD_SHOWN:
            check = {"kind": "build", "verdict": hydra["verdict"]}
            if hydra.get("condition"):
                check["condition"] = True
            package = hydra["package"]
        elif update.get("verdict") in UPDATE_SHOWN:
            check = {"kind": "update", "verdict": update["verdict"]}
            if update.get("now"):
                check["now"] = update["now"]
            package = update["package"]
        else:
            continue
        checked.setdefault(package_key(package), []).append(
            {
                "number": issue["n"],
                "title": issue["title"],
                "url": ISSUE_URL + str(issue["n"]),
                **check,
            }
        )
    return {"prs": by_number, "fixes": fixes, "issues": checked, "open": open_prs}


def add_facts(rows, digest):
    """Give each row the digest's findings for its own package (facts'): its
    update PR's ("openPR"'s "facts", with "fixesBuild" when it touches the
    package while its build fails on Hydra), the other open PRs that do
    ("fixPRs"), its other open PRs ("otherPRs", a removal first, then the
    newest), and its checked issues ("issueChecks"), at most SHOWN of each;
    and "dropPR" when an open PR removes it from nixpkgs (the list's
    badge). Replaces the last sync's."""
    found = (digest or {}).get("facts")
    for row in rows:
        for field in ("fixPRs", "issueChecks", "otherPRs", "dropPR"):
            row.pop(field, None)
        if not found:
            continue
        pr = row.get("openPR")
        if pr and (theirs := found["prs"].get(pr["number"])):
            pr["facts"] = dict(theirs)
        keys = {package_key(a) for a in [row["name"], *(row.get("attrs") or [])]}
        # The update PR is said once: as the update PR, which touches the
        # failing build too, not again among the fixes.
        if pr and any(
            fix["number"] == pr["number"]
            for key in keys
            for fix in found["fixes"].get(key, [])
        ):
            pr.setdefault("facts", {})["fixesBuild"] = True
        for field, source in (("fixPRs", "fixes"), ("issueChecks", "issues")):
            items, seen = [], {pr["number"]} if pr and field == "fixPRs" else set()
            for key in sorted(keys):
                for item in found[source].get(key, []):
                    if item["number"] not in seen:
                        seen.add(item["number"])
                        items.append(item)
            if items:
                row[field] = items[:SHOWN]
        # Its other open PRs: not the update PR nor the fixes (said above).
        said = {pr["number"]} if pr else set()
        said |= {fix["number"] for fix in row.get("fixPRs") or []}
        others = {}
        for key in keys:
            for item in found.get("open", {}).get(key, []):
                if item["number"] not in said:
                    others[item["number"]] = item
        ordered = sorted(
            others.values(), key=lambda p: (p.get("kind") != "drop", -p["number"])
        )
        if ordered:
            row["otherPRs"] = ordered[:SHOWN]
        # Being removed: when the title names the row's own package (not one
        # of its other attributes: "sqlite-interactive: drop" leaves sqlite).
        mine = package_key(row["name"])
        if drop := next(
            (
                p
                for p in ordered
                if p.get("kind") == "drop"
                and (m := TITLE_PACKAGE.match(p["title"]))
                and package_key(m.group(1)) == mine
            ),
            None,
        ):
            row["dropPR"] = {"number": drop["number"], "title": drop["title"]}


def recent(at, now):
    """Whether a list made at (ISO) is recent enough to use."""
    if not at:
        return False
    age = datetime.fromisoformat(now) - datetime.fromisoformat(at)
    return age <= timedelta(hours=config.PRS_DIGEST_MAX_AGE_HOURS)


def node(pr):
    """A PR as github_bulk's listings have it (GraphQL's names)."""
    return {
        "number": pr["n"],
        "title": pr["title"],
        "url": PR_URL + str(pr["n"]),
        "isDraft": pr.get("draft", False),
        "baseRefName": pr.get("base"),
    }


def _read(base, name):
    """A file of the digest (name), as written."""
    data = json.loads(http.get(base + name, compressed=True) or "null")
    if not data or data.get("format") != FORMAT:
        raise ValueError(f"no {name} in a format this nixkeeper reads")
    return data


def _list(base, name, key):
    """A list of the digest (name: its file), as written: its key's items."""
    return _read(base, name).get(key) or []


def load(now, revision):
    """{"open": (PRs, issues) or None, "merged": PRs or None, "facts"?:
    the digest's findings, with the open lists (facts)}, as
    github_bulk's listings give them (each None when it's not recent, or
    merged when listed since another channel commit than revision), or None
    (saying why) when it's turned off or can't be read."""
    base = config.PRS_DIGEST_URL
    if not base:
        return None
    try:
        meta = json.loads(http.get(base + "meta.json") or "null")
        if not meta or meta.get("format") != FORMAT:
            raise ValueError(f"no digest in a format this nixkeeper reads ({base})")
        issues_meta = meta.get("issues") or {}
        merged_meta = meta.get("merged") or {}
        found = {"open": None, "merged": None}
        why = []
        if recent(meta.get("generatedAt"), now) and recent(issues_meta.get("at"), now):
            data = _read(base, "prs.json")
            raw_issues = _list(base, "issues.json", "issues")
            prs = [node(p) for p in data.get("prs") or []]
            issues = [{"number": i["n"], "title": i["title"]} for i in raw_issues]
            found["open"] = (prs, issues)
            found["facts"] = facts(
                data.get("prs") or [], data.get("groups") or [], raw_issues
            )
        else:
            why.append("open PRs and issues too old")
        if merged_meta.get("revision") != revision:
            why.append("merged PRs since another channel commit")
        elif not recent(merged_meta.get("at"), now):
            why.append("merged PRs too old")
        else:
            found["merged"] = [
                node(p) for p in _list(base, "merged.json", "prs") if p.get("n")
            ]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note("prs", False, f"couldn't be read ({e})")
        print(
            f"::warning::PRs digest: couldn't use it ({e}); listing them here",
            file=sys.stderr,
        )
        return None
    used = found["open"] is not None or found["merged"] is not None
    about.note(
        "prs",
        used,
        "; ".join(why) if not used else None,
        at=meta.get("generatedAt"),
        prs=len(found["open"][0]) if found["open"] else None,
        issues=len(found["open"][1]) if found["open"] else None,
        merged=len(found["merged"]) if found["merged"] is not None else None,
        partly="; ".join(why) if used and why else None,
    )
    print(
        f"PRs digest: made {meta.get('generatedAt')}"
        + (
            f", {len(found['open'][0]):,} open PRs, {len(found['open'][1]):,} issues"
            if found["open"]
            else ""
        )
        + (
            f", {len(found['merged']):,} merged since the channel"
            if found["merged"] is not None
            else ""
        )
        + (f" ({'; '.join(why)}: listed here)" if why else ""),
        file=sys.stderr,
    )
    return found
