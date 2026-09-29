"""nixpkgs-update (the r-ryantm bot): the outcome of its latest attempt to
update each tracked package, read from its public logs. The logs carry no exit
code, so the outcome is recognised from how the log reads (the approach of
github.com/asymmetric/nixpkgs-update-notifier)."""

import re
import sys
import time
import urllib.error

from .. import config, history
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


def superseded(attempt, nix_version):
    """Whether nixpkgs has moved on since the attempt (someone updated it
    another way), so its failure no longer matters. Unknown (False) when the
    log doesn't say what nixpkgs had then."""
    was = attempt.get("was")
    if not was or not nix_version:
        return False
    # A name-version ends in the version: wesnoth-devel-1.19.24.
    return was != nix_version and not was.endswith(f"-{nix_version}")


def add_attempts(rows, nixpkgs, previous, now):
    """Give every row in nixpkgs the bot's latest attempt ("update", None if
    it never tried) and whether that failed ("updateFailure"). With several
    attrs, the most recently attempted one counts. A row whose lookup fails
    keeps the previous run's result and is marked as not refreshed."""
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
        if (
            attempt
            and attempt["outcome"] == "failed"
            and superseded(attempt, row.get("nixVersion"))
        ):
            attempt["outcome"] = "superseded"
        row["update"] = attempt
        row["updateFailure"] = bool(attempt and attempt["outcome"] == "failed")
    if failed:
        print(
            f"::warning::{failed} nixpkgs-update log lookups failed; those show "
            "the previous run's result",
            file=sys.stderr,
        )
