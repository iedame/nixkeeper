"""The status issue: one GitHub issue in this repo showing what needs attention,
rewritten every sync, plus a comment (which is what notifies) when something
changed for the worse. Only runs that set --notify or NIXKEEPER_NOTIFY post
(the workflows do); see notify() for the methods."""

import os
import sys
import urllib.error
import urllib.parse
from datetime import datetime

from . import config
from .changes import (
    NOTIFY,
    STALE_LABELS,
    broken_builds,
    build_label,
    diff,
    failed_builds,
    failures,
    is_outdated,
    on_master,
    should_notify,
    stale_sources,
    waiting_for_channel,
)
from .sources import github

TITLE = "nixkeeper status"


def days_text(since, now):
    days = (datetime.fromisoformat(now) - datetime.fromisoformat(since)).days
    return "today" if days < 1 else "1 day" if days == 1 else f"{days} days"


def cves_url(project):
    """Repology's list of CVEs for a project, with the versions they affect.
    (Its API only says whether a version is vulnerable, not to what.)"""
    return f"https://repology.org/project/{urllib.parse.quote(project)}/cves"


def describe(row, now):
    """One package, as a bullet's text."""
    text = f"`{row['name']}`"
    if is_outdated(row):
        text += f" {row['nixVersion']} → {row.get('refVersion') or '?'}"
        upstream = row.get("upstream") or {}
        if upstream.get("newer") and upstream["version"] == row.get("refVersion"):
            text += " (found by nixkeeper's update check)"
        if row.get("outdatedSince"):
            text += f" · outdated {days_text(row['outdatedSince'], now)}"
        if waiting_for_channel(row):
            text += f" · on master ({on_master(row)}), waiting for nixos-unstable"
            if pr := row.get("masterPR"):
                text += f" ([#{pr['number']}]({pr['url']}))"
        elif pr := row.get("openPR"):
            state = "draft PR" if pr["draft"] else "PR"
            text += f" · {state} [#{pr['number']}]({pr['url']}) open"
    if failures(row):
        text += " — " + ", ".join(failures(row))
    if row.get("nixVulnerable"):
        text += " — flagged vulnerable"
        if row.get("project"):
            text += f" ([known CVEs]({cves_url(row['project'])}))"
    logs = [
        f"[{build_label(row, b)} log]({config.HYDRA_URL}/build/{b['build']}/log)"
        for b in failed_builds(row)
    ]
    update = row.get("update")
    if row.get("updateFailure") and update:
        logs.append(f"[update log]({update['log']})")
    if logs:
        text += " · " + " · ".join(logs)
    broken = [build_label(row, b) for b in broken_builds(row)]
    if broken:
        text += " — marked broken in nixpkgs on " + ", ".join(broken)
    if row.get("staleSince"):
        text += (
            f" — {STALE_LABELS['repology']}, showing data from {row['staleSince'][:10]}"
        )
    for source, info in (row.get("notRefreshed") or {}).items():
        text += (
            f" — {STALE_LABELS[source]} since {info['since'][:10]}: {info['reason']}"
        )
    return text


def bullets(rows, now):
    return "\n".join(f"- {describe(row, now)}" for row in rows)


CHANGE_LABELS = {
    "outdated": "Newly outdated",
    "failed": "Newly failed",
    "vulnerable": "Newly flagged vulnerable",
    "notRefreshed": "Not refreshed",
    "refreshed": "Refreshed again",
    "caughtUp": "Caught up",
    "fixed": "No longer failing",
    "broken": "Marked broken in nixpkgs",
    "added": "Now tracked",
    "removed": "No longer tracked",
}


def change_lines(changes, kinds, now):
    lines = []
    for kind in kinds:
        items = changes[kind]
        if not items:
            continue
        names = ", ".join(
            f"`{i}`" if isinstance(i, str) else describe(i, now) for i in items
        )
        lines.append(f"- **{CHANGE_LABELS[kind]}:** {names}")
    return lines


def status_body(rows, changes, now, page_url=None):
    """The issue body: current state, then everything that changed this run."""
    sections = [
        ("Failed", [r for r in rows if failures(r)]),
        (
            "Outdated",
            sorted(
                (r for r in rows if is_outdated(r)),
                key=lambda r: r.get("outdatedSince") or "~",
            ),
        ),
        ("Flagged vulnerable", [r for r in rows if r.get("nixVulnerable")]),
        ("Marked broken in nixpkgs", [r for r in rows if broken_builds(r)]),
        ("Not refreshed", [r for r in rows if stale_sources(r)]),
    ]
    parts = [
        f"Checked {now[:16].replace('T', ' ')} UTC · {len(rows)} packages tracked"
        + (f" · [open the page]({page_url})" if page_url else "")
    ]
    if not any(items for _, items in sections):
        parts.append("Nothing needs attention.")
    for title, items in sections:
        if items:
            parts.append(f"### {title} ({len(items)})\n{bullets(items, now)}")
    changed = change_lines(changes, CHANGE_LABELS, now)
    parts.append(
        "### Since the previous sync\n"
        + ("\n".join(changed) if changed else "No changes.")
    )
    parts.append(
        "<sub>Updated by the daily sync. A comment is posted when something newly "
        "needs attention; close this issue to reset it (the next sync opens a new "
        "one).</sub>"
    )
    return "\n\n".join(parts)


def change_comment(changes, now):
    return "\n".join(
        [f"**Changes in the {now[:10]} sync**", "", *change_lines(changes, NOTIFY, now)]
    )


def page_url(repo=None):
    """Where the page lives, for links: NIXKEEPER_PAGE_URL, else the GitHub
    Pages project site of owner/repo, else None."""
    if os.environ.get("NIXKEEPER_PAGE_URL"):
        return os.environ["NIXKEEPER_PAGE_URL"]
    if not repo:
        return None
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


def github_issue(rows, changes, now):
    """The status issue in NIXKEEPER_GITHUB_REPO (in a workflow, the
    workflow's own repository). Needs a token given explicitly: the local gh
    login is never used to post."""
    repo = os.environ.get("NIXKEEPER_GITHUB_REPO") or os.environ.get(
        "GITHUB_REPOSITORY"
    )
    token = github.token(use_gh=False)
    if not repo or not token:
        print(
            "::warning::github-issue notifications need a repository "
            "(NIXKEEPER_GITHUB_REPO) and a token (NIXKEEPER_GITHUB_TOKEN_FILE or "
            "GITHUB_TOKEN)",
            file=sys.stderr,
        )
        return
    comment = change_comment(changes, now) if should_notify(changes) else None
    number = github.update_status_issue(
        repo, token, TITLE, status_body(rows, changes, now, page_url(repo)), comment
    )
    print(
        f"Updated status issue #{number}" + (" and commented" if comment else ""),
        file=sys.stderr,
    )


# How to notify, by NIXKEEPER_NOTIFY. Another way (ntfy, email, ...) is a
# function taking (rows, changes, now), added here.
SENDERS = {"github-issue": github_issue}
# Earlier name for github-issue, still accepted.
ALIASES = {"1": "github-issue"}


def notify(previous, rows, now):
    """Send what changed the way NIXKEEPER_NOTIFY says (unset or "none": not
    at all, as in local runs). Never fails the sync: a problem here is
    reported as a workflow warning."""
    method = config.NOTIFY or os.environ.get("NIXKEEPER_NOTIFY") or "none"
    method = ALIASES.get(method, method)
    if method == "none":
        print(
            "Not notifying (notify: none; the GitHub workflows use github-issue).",
            file=sys.stderr,
        )
        return
    if method not in SENDERS:
        print(
            f"::warning::{method} isn't a notification method "
            f"({', '.join(['none', *SENDERS])})",
            file=sys.stderr,
        )
        return
    try:
        SENDERS[method](rows, diff(previous, rows), now)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"::warning::Couldn't notify ({method}): {e}", file=sys.stderr)
