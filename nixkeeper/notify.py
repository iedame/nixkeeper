"""The status issues: GitHub issues in this repo showing what needs
attention, rewritten every sync, plus a comment (which is what notifies)
when something changed for the worse. The instance's own ("nixkeeper
status", everything on its lists; off with `statusIssue = false;` in the
lists), and one for each maintainer or team in notifications/ ("nixkeeper
status: iedame"), with only their packages. Only runs that set --notify or
NIXKEEPER_NOTIFY post (the workflows do); see notify() for the methods."""

import os
import re
import sys
import time
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
    is_vulnerable,
    on_master,
    should_notify,
    stale_sources,
    waiting_for_channel,
)
from .sources import github
from .sources import nixpkgs as nixpkgs_source

TITLE = "nixkeeper status"
# Between one subscriber's issue and the next: GitHub limits how fast
# content is created.
SUBSCRIBER_PAUSE = 1.0


def days_text(since, now):
    days = (datetime.fromisoformat(now) - datetime.fromisoformat(since)).days
    return "today" if days < 1 else "1 day" if days == 1 else f"{days} days"


def cves_url(project):
    """Repology's list of CVEs for a project, with the versions they affect.
    (Its API only says whether a version is vulnerable, not to what.)"""
    return f"https://repology.org/project/{urllib.parse.quote(project)}/cves"


def pr_number(pr):
    """A nixpkgs PR's number, in code: never a link. A link to the PR (or
    its address) puts "mentioned this pull request" on the nixpkgs PR each
    time the issue is rewritten; a bare #number would link this repository's
    issue of that number instead."""
    return f"`#{pr['number']}`"


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
                text += f" ({pr_number(pr)})"
        elif pr := row.get("openPR"):
            state = "draft PR" if pr["draft"] else "PR"
            text += f" · {state} {pr_number(pr)} open"
    if failures(row):
        text += " — " + ", ".join(failures(row))
    if row.get("markedInsecure"):
        text += " — marked insecure in nixpkgs"
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
    "vulnerable": "Newly vulnerable",
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
        ("Vulnerable", [r for r in rows if is_vulnerable(r)]),
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
    """Where the page lives, for links: NIXKEEPER_PAGE_URL (the workflows: the
    instance's own site, when it has one), else the GitHub Pages project site
    of owner/repo, else None."""
    if os.environ.get("NIXKEEPER_PAGE_URL"):
        return os.environ["NIXKEEPER_PAGE_URL"]
    if not repo:
        return None
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


# notifications/'s folders, and the field each file in them has.
FOLDERS = {"maintainers": "maintainer", "teams": "team"}


def read_subscribers(path=None):
    """Who gets a status issue of their own: {"maintainers/iedame":
    {"maintainer": handle}, "teams/gaming": {"team": name, "mention":
    [handles]}}, from notifications/ (config.notifications_path();
    nix/notifications.nix checks the format). {} without the folder. One
    that doesn't make sense (or isn't in its kind's folder) is left out,
    said so."""
    path = path or config.notifications_path()
    if not os.path.exists(path):
        print(
            f"No notifications/ at {path}: no status issues of their own.",
            file=sys.stderr,
        )
        return {}
    try:
        read = nixpkgs_source.read_lists(path)
    except SystemExit as e:  # didn't evaluate: the sync goes on without them
        print(f"::warning::notifications/ not read: {e}", file=sys.stderr)
        return {}
    found = {}
    for folder, kind in FOLDERS.items():
        for name, sub in sorted((read.get(folder) or {}).items()):
            mention = sub.get("mention", []) if isinstance(sub, dict) else None
            if (
                not isinstance(sub, dict)
                or not isinstance(sub.get(kind), str)
                or not sub[kind]
                or set(FOLDERS.values()) - {kind} & set(sub)
                or not isinstance(mention, list)
                or not all(isinstance(m, str) and m for m in mention)
            ):
                print(
                    f"::warning::notifications/{folder}/{name}.nix: needs {kind} "
                    "(and mention, a list of handles, if any): left out",
                    file=sys.stderr,
                )
                continue
            found[f"{folder}/{name}"] = sub
    return found


def read_lists():
    """The package lists, for their settings (statusIssue); {} when they
    can't be read, which never stops a run."""
    try:
        return nixpkgs_source.read_lists()
    except SystemExit as e:
        print(f"::warning::package lists not read for notifying: {e}", file=sys.stderr)
        return {}


def subscriber_title(sub):
    """ "nixkeeper status: @iedame" or "nixkeeper status: Gaming team": a
    handle and a team of the same name never share an issue."""
    if "maintainer" in sub:
        return f"{TITLE}: @{sub['maintainer']}"
    return f"{TITLE}: {sub['team']} team"


def mentions(sub):
    """The handles a subscriber's issue mentions (which subscribes them)."""
    handles = [sub["maintainer"]] if "maintainer" in sub else []
    return [*handles, *sub.get("mention", [])]


def is_subscribed(sub, row):
    """Whether row is one of sub's packages: listing the maintainer, or under
    the team (meta.teams, or a list named after it). Not in a set updated in
    bulk, as the page's counts."""
    if row.get("set"):
        return False
    if "maintainer" in sub:
        handle = sub["maintainer"].lower()
        return any(m.lower() == handle for m in row.get("maintainers") or [])
    team = sub["team"].lower()
    return any(t.lower() == team for t in row.get("teams") or [])


def subscriber_page(base, sub):
    """The page showing sub's packages: ?q=@handle, or ?team=."""
    if not base:
        return None
    query = (
        {"q": f"@{sub['maintainer']}"} if "maintainer" in sub else {"team": sub["team"]}
    )
    return f"{base.rstrip('/')}/?{urllib.parse.urlencode(query)}"


def subscriber_body(sub, rows, changes, now, base):
    who = (
        f"@{sub['maintainer']}'s packages"
        if "maintainer" in sub
        else f"The {sub['team']} team's packages"
        + (
            f" · for {' '.join(f'@{m}' for m in sub.get('mention', []))}"
            if sub.get("mention")
            else ""
        )
    )
    return (
        f"{who}, as [nixkeeper]({base or 'https://github.com/iedame/nixkeeper'}) "
        "sees them.\n\n"
        + status_body(rows, changes, now, subscriber_page(base, sub))
        + "\n\n<sub>From notifications/ in this repository: removing the file "
        "closes this issue.</sub>"
    )


def subscriber_issues(
    repo, token, subscribers, previous, everyone, now, news_only=False
):
    """Each subscriber's issue, with only their packages; and closing those
    whose file is gone. news_only (the hourly checks): only the issues of
    those whose packages newly need attention, and none closed: the daily
    sync rewrites them all."""
    github.ensure_label(
        repo,
        token,
        github.SUBSCRIBER_LABEL,
        "A maintainer's or team's status issue (notifications/)",
    )
    issues = github.open_issues(repo, token, github.SUBSCRIBER_LABEL)
    base = page_url(repo)
    wanted = set()
    for sub in subscribers.values():
        title = subscriber_title(sub)
        wanted.add(title)
        rows = [r for r in everyone if is_subscribed(sub, r)]
        before = {
            **previous,
            "packages": [r for r in previous["packages"] if is_subscribed(sub, r)],
        }
        changes = diff(before, rows)
        news = should_notify(changes)
        if news_only and not news:
            continue
        comment = change_comment(changes, now) if news else None
        number = github.write_issue(
            repo,
            token,
            issues.get(title),
            title,
            subscriber_body(sub, rows, changes, now, base),
            github.SUBSCRIBER_LABEL,
            comment,
        )
        print(
            f"Updated {title!r} (#{number}, {len(rows)} packages)"
            + (" and commented" if comment else ""),
            file=sys.stderr,
        )
        time.sleep(SUBSCRIBER_PAUSE)
    for title, number in sorted(issues.items()):
        if news_only:
            break
        if re.match(re.escape(TITLE) + ": ", title) and title not in wanted:
            github.close_issue(
                repo,
                token,
                number,
                "Its file in notifications/ is gone: no longer updated.",
            )
            print(f"Closed {title!r} (#{number}): no file for it", file=sys.stderr)


def github_issue(
    rows,
    changes,
    now,
    previous=None,
    everyone=None,
    lists=None,
    subscribers=None,
    news_only=False,
):
    """The status issues in NIXKEEPER_GITHUB_REPO (in a workflow, the
    workflow's own repository): the instance's own, for rows (unless the
    lists turn it off: closed then), and the subscribers' (notifications/),
    each with its packages among everyone. Needs a token given explicitly:
    the local gh login is never used to post."""
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
    if (lists or {}).get("statusIssue", True) is False:
        for number in github.open_issues(repo, token, github.STATUS_LABEL).values():
            github.close_issue(
                repo,
                token,
                number,
                "Turned off (`statusIssue = false;` in the package lists): no "
                "longer updated. Status issues of their own are in "
                "notifications/.",
            )
            print(f"Closed the status issue #{number}: turned off", file=sys.stderr)
    else:
        comment = change_comment(changes, now) if should_notify(changes) else None
        number = github.update_status_issue(
            repo, token, TITLE, status_body(rows, changes, now, page_url(repo)), comment
        )
        print(
            f"Updated status issue #{number}" + (" and commented" if comment else ""),
            file=sys.stderr,
        )
    if subscribers:
        subscriber_issues(
            repo, token, subscribers, previous, everyone or rows, now, news_only
        )


# How to notify, by NIXKEEPER_NOTIFY. Another way (ntfy, email, ...) is a
# function taking (rows, changes, now, **context), added here.
SENDERS = {"github-issue": github_issue}
# Earlier name for github-issue, still accepted.
ALIASES = {"1": "github-issue"}


def notify(
    previous,
    rows,
    now,
    everyone=None,
    everyone_before=None,
    lists=None,
    news_only=False,
):
    """Send what changed the way NIXKEEPER_NOTIFY says (unset or "none": not
    at all, as in local runs). rows: the instance's own (its lists');
    everyone: every row, with everyone_before the previous run's (with every
    package: all of nixpkgs), for the subscribers' issues; lists: the package
    lists (statusIssue; read here when not given, as by the hourly checks:
    without them, a turned-off status issue came back); news_only (the hourly
    checks): subscribers' issues only where their packages newly need
    attention. Never fails the sync: a problem here is reported as a workflow
    warning."""
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
        if lists is None:
            lists = read_lists()
        subscribers = read_subscribers()
        SENDERS[method](
            rows,
            diff(previous, rows),
            now,
            previous=everyone_before or previous,
            everyone=everyone or rows,
            lists=lists,
            subscribers=subscribers,
            news_only=news_only,
        )
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"::warning::Couldn't notify ({method}): {e}", file=sys.stderr)
