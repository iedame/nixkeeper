"""nixpkgs-update (the r-ryantm bot): the outcome of its latest attempt to
update each tracked package, read from its public logs. The logs carry no exit
code, so the outcome is recognised from how the log reads (the approach of
github.com/asymmetric/nixpkgs-update-notifier)."""

import re
import sys
import time
import urllib.error

from .. import config, history
from ..changes import on_master
from ..rows import search_term
from . import http

LOG_NAME = re.compile(r'href="(\d{4}-\d{2}-\d{2})\.log"')
# "UPDATE_INFO: egoboo 2.7.3 -> 2.8.1 https://..."; "0 -> 1" when the
# package's own updateScript decides the version.
UPDATE_INFO = re.compile(r"UPDATE_INFO: \S+ (\S+) -> (\S+)")
UPDATE_SCRIPT = "0"  # the "from" of an updateScript attempt
# With an updateScript, what nixpkgs had shows as its name-version instead:
# "Going to be running update for following packages:\n - wesnoth-devel-1.19.24".
UPDATE_SCRIPT_PACKAGE = re.compile(
    r"Going to be running update for following packages:\s*\n\s*- (\S+)"
)
PR = re.compile(r"api\.github\.com/repos/NixOS/nixpkgs/(?:pulls|issues)/(\d+)")
PR_EXISTS = "There might already be an open PR"
NO_CHANGE = (
    "The diff was empty after rewrites",
    "Package version did not change",
    # Someone updated it before the bot got to it.
    "not present in master derivation file",
)
# nix build errors, nixpkgs-update's own, and update script errors.
FAILED = re.compile(r"^error:|ExitFailure|failed with", re.MULTILINE)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
EXCERPT_LINES = 3


def attempts_url(attr):
    return f"{config.NIXPKGS_UPDATE_LOGS_URL}/{search_term(attr)}/"


def latest_date(attr):
    """Date of the bot's latest attempt at attr, or None if it never tried."""
    listing = http.get(attempts_url(attr))
    time.sleep(1)  # be polite
    dates = LOG_NAME.findall(listing or "")
    return max(dates) if dates else None


def excerpt(log):
    """The last few meaningful lines: where a failed build stops is usually
    the reason (the ExitFailure line itself just says "Received ExitFailure")."""
    lines = [
        ANSI.sub("", line).rstrip()[:200]
        for line in log.splitlines()
        if line.strip() and not line.startswith("@nix")
    ]
    return lines[-EXCERPT_LINES:]


def parse(log):
    """{"outcome", "from"?, "to"?, "was"?, "pr"?, "excerpt"?} for one log.
    outcome: prOpened, prExists, noChange, failed, or other. was: what
    nixpkgs had when the bot tried, as a version (2.7.3) or, with an
    updateScript, a name-version (wesnoth-devel-1.19.24)."""
    result = {}
    if info := UPDATE_INFO.search(log):
        result["from"], result["to"] = info.groups()
        if result["from"] != UPDATE_SCRIPT:
            result["was"] = result["from"]
    if "was" not in result and (package := UPDATE_SCRIPT_PACKAGE.search(log)):
        result["was"] = package.group(1)
    prs = PR.findall(log)
    if PR_EXISTS in log:
        result["outcome"] = "prExists"
    elif prs:
        result["outcome"] = "prOpened"
    elif any(text in log for text in NO_CHANGE):
        result["outcome"] = "noChange"
    elif FAILED.search(log):
        result.update(outcome="failed", excerpt=excerpt(log))
    else:
        result["outcome"] = "other"
    if prs and result["outcome"] in ("prExists", "prOpened"):
        result["pr"] = int(prs[-1])
    return result


def latest_attempt(attr):
    """The bot's latest attempt at attr: {"attr", "date", "outcome", ...}, or
    None if it never tried."""
    date = latest_date(attr)
    if date is None:
        return None
    url = f"{attempts_url(attr)}{date}.log"
    log = http.get(url) or ""
    time.sleep(1)
    return {"attr": attr, "date": date, "log": url, **parse(log)}


def moved_on(attempt, version):
    """Whether version differs from what nixpkgs had when the bot tried.
    Unknown (False) when the log doesn't say what that was."""
    was = attempt.get("was")
    if not was or not version:
        return False
    # A name-version ends in the version: wesnoth-devel-1.19.24.
    return was != version and not was.endswith(f"-{version}")


def superseded(attempt, nix_version, master=None):
    """Where nixpkgs has moved on since the attempt (someone updated it
    another way), so its failure no longer matters: "nixos-unstable" (the
    channel), "master" (merged, not in the channel yet), or None."""
    if moved_on(attempt, nix_version):
        return "nixos-unstable"
    if moved_on(attempt, master):
        return "master"
    return None


def recheck_superseded(rows):
    """Mark failures superseded that are, now that more is known about master
    (an update PR merged there, found after the logs were read): so a row
    waiting for the channel doesn't also show as failed."""
    for row in rows:
        attempt = row.get("update")
        if not attempt or attempt.get("outcome") != "failed":
            continue
        where = superseded(attempt, row.get("nixVersion"), on_master(row))
        if where:
            attempt.update(outcome="superseded", supersededOn=where)
            row["updateFailure"] = False


def ignored(attempt, rules):
    """The reason a manual rule gives for ignoring the version a failed
    attempt tried to update to, or None. rules: {version: reason}, the row's
    entry in package-lists/ignored-updates.nix."""
    if attempt.get("outcome") != "failed":
        return None
    return (rules or {}).get(attempt.get("to"))


def add_attempts(rows, nixpkgs, previous, now, ignored_updates=None):
    """Give every row in nixpkgs the bot's latest attempt ("update", None if
    it never tried) and whether that failed ("updateFailure"). With several
    attrs, the most recently attempted one counts. A row whose lookup fails
    keeps the previous run's result and is marked as not refreshed.
    ignored_updates: {row name: {version: reason}}, versions whose failed
    attempts count as superseded (a version that was never really released,
    say)."""
    ignored_updates = ignored_updates or {}
    print("Checking nixpkgs-update logs...", file=sys.stderr)
    before = {row["name"]: row for row in previous["packages"]}
    failed = consecutive = 0
    for row in rows:
        attrs = [a for a in row["attrs"] if a in nixpkgs]
        if not attrs:
            continue  # not in nixpkgs: nothing for the bot to update
        down = consecutive >= config.UPDATE_LOGS_MAX_CONSECUTIVE_FAILURES
        try:
            if down:
                raise OSError("not asked: it didn't answer earlier lookups")
            attempts = [a for a in map(latest_attempt, attrs) if a]
            consecutive = 0
        except (urllib.error.URLError, OSError) as e:
            failed += 1
            consecutive += not down
            if not down:
                print(f"  {row['name']}: {e}", file=sys.stderr)
            old = before.get(row["name"], {})
            row["update"] = old.get("update")
            row["updateFailure"] = bool(old.get("updateFailure"))
            history.not_refreshed(
                row, "update", f"couldn't read the nixpkgs-update logs ({e})", old, now
            )
            continue
        attempt = max(attempts, key=lambda a: a["date"], default=None)
        # "master" comes from Hydra, read before this.
        where = (
            attempt
            and attempt["outcome"] == "failed"
            and superseded(attempt, row.get("nixVersion"), row.get("master"))
        )
        if where:
            attempt.update(outcome="superseded", supersededOn=where)
        elif attempt and (reason := ignored(attempt, ignored_updates.get(row["name"]))):
            attempt.update(outcome="superseded", supersededOn="ignored", reason=reason)
        for version in ignored_updates.get(row["name"]) or {}:
            if not attempt or attempt.get("to") != version:
                print(
                    f"::notice::ignoredUpdates.{row['name']}: the bot's latest "
                    f"attempt isn't at {version} anymore; the rule can go",
                    file=sys.stderr,
                )
        row["update"] = attempt
        row["updateFailure"] = bool(attempt and attempt["outcome"] == "failed")
    if failed:
        print(
            f"::warning::{failed} nixpkgs-update log lookups failed; those show "
            "the previous run's result",
            file=sys.stderr,
        )
