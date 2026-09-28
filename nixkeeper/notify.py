"""The status issue: one GitHub issue in this repo showing what needs attention,
rewritten every sync, plus a comment (which is what notifies) when something
changed for the worse. Only CI posts: it sets NIXKEEPER_NOTIFY=1."""

import os
import sys
import urllib.error
from datetime import datetime

from . import config
from .changes import (
    NOTIFY,
    broken_builds,
    build_label,
    diff,
    failed_builds,
    failures,
    is_outdated,
    should_notify,
)
from .sources import github

TITLE = "nixkeeper status"


def days_text(since, now):
    days = (datetime.fromisoformat(now) - datetime.fromisoformat(since)).days
    return "today" if days < 1 else "1 day" if days == 1 else f"{days} days"


def describe(row, now):
    """One package, as a bullet's text."""
    text = f"`{row['name']}`"
    if is_outdated(row):
        text += f" {row['nixVersion']} → {row.get('refVersion') or '?'}"
        if row.get("outdatedSince"):
            text += f" · outdated {days_text(row['outdatedSince'], now)}"
    if failures(row):
        text += " — " + ", ".join(failures(row))
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
        text += f" — Repology lookup failed, showing data from {row['staleSince'][:10]}"
    return text


def bullets(rows, now):
    return "\n".join(f"- {describe(row, now)}" for row in rows)


CHANGE_LABELS = {
    "outdated": "Newly outdated",
    "failed": "Newly failed",
    "vulnerable": "Newly flagged vulnerable",
    "notRefreshed": "Not refreshed",
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
        ("Not refreshed", [r for r in rows if r.get("staleSince")]),
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


def page_url(repo):
    """The GitHub Pages project site for owner/repo."""
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


def notify(previous, rows, now):
    """Update the status issue, commenting if something newly needs attention.
    Never fails the sync: a problem here is reported as a workflow warning."""
    if os.environ.get("NIXKEEPER_NOTIFY") != "1":
        print(
            "Not updating the status issue (only CI does, with NIXKEEPER_NOTIFY=1).",
            file=sys.stderr,
        )
        return
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print(
            "::warning::NIXKEEPER_NOTIFY is set but GITHUB_REPOSITORY or "
            "GITHUB_TOKEN is missing",
            file=sys.stderr,
        )
        return
    changes = diff(previous, rows)
    comment = change_comment(changes, now) if should_notify(changes) else None
    try:
        number = github.update_status_issue(
            repo, token, TITLE, status_body(rows, changes, now, page_url(repo)), comment
        )
        print(
            f"Updated status issue #{number}" + (" and commented" if comment else ""),
            file=sys.stderr,
        )
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"::warning::Couldn't update the status issue: {e}", file=sys.stderr)
