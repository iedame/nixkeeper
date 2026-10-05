"""nixpkgs-update (the r-ryantm bot): the outcome of its latest attempt to
update each tracked package, read from its public logs. The logs carry no exit
code, so the outcome is recognised from how the log reads (the approach of
github.com/asymmetric/nixpkgs-update-notifier)."""

import copy
import re
import sys
import time
import urllib.error
import urllib.parse
from datetime import UTC, datetime, timedelta

from .. import config, history
from ..changes import is_outdated, on_master
from ..rows import search_term
from . import http

LOG_NAME = re.compile(r'href="(\d{4}-\d{2}-\d{2})\.log"')
# The version of parse()'s rules, stored with each attempt ("parser"). A sync
# reuses the previous run's reading of a log it has already read (same
# attribute, same date) instead of downloading it again, but only one read
# with these same rules: bump this whenever parse() changes how it reads a
# log, so the next sync reads every log again and the change applies at once.
PARSER = 2
# What add_attempts adds to an attempt after reading its log, from the
# state of nixpkgs and the rules at the time; as_read() takes them off.
JUDGED = ("supersededOutcome", "supersededOn", "reason", "community")
# "UPDATE_INFO: egoboo 2.7.3 -> 2.8.1 https://..."; "0 -> 1" when the
# package's own updateScript decides the version.
UPDATE_INFO = re.compile(r"UPDATE_INFO: \S+ (\S+) -> (\S+)")
UPDATE_SCRIPT = "0"  # the "from" of an updateScript attempt
UPDATE_SCRIPT_TO = "1"  # and its "to", before the script runs
# With an updateScript, what nixpkgs had shows as its name-version instead:
# "Going to be running update for following packages:\n - wesnoth-devel-1.19.24".
UPDATE_SCRIPT_PACKAGE = re.compile(
    r"Going to be running update for following packages:\s*\n\s*- (\S+)"
)
DIFF_HEAD = "Diff after rewrites:\n"
PR = re.compile(r"api\.github\.com/repos/NixOS/nixpkgs/(?:pulls|issues)/(\d+)")
PR_EXISTS = "There might already be an open PR"
# Every rewriter left the package as it was. After an updateScript attempt
# ("0 -> 1") that means there was nothing to update; after a real version
# ("1.37 -> 1.38"), that the bot has no way to update this package.
EMPTY_DIFF = "The diff was empty after rewrites"
# Why the rewriters that could have applied didn't: "[version] generic
# version rewriter does not support multiple hashes".
REWRITER = re.compile(r"^\[(?:version|updateScript)\] (\S.*)$", re.MULTILINE)
NO_CHANGE = (
    EMPTY_DIFF,
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


# The log site's front page lists every package's directory with when it
# last changed (nginx, in UTC): "<a href="unciv/">unciv/</a>   03-Oct-2026 00:00".
DIRECTORY = re.compile(
    r'<a href="([^"/]+)/">[^<]*</a>\s+(\d{2}-[A-Z][a-z]{2}-\d{4} \d{2}:\d{2})'
)
# Fewer than this many directories: not the page it should be.
MIN_DIRECTORIES = 1000


def directory_dates():
    """{directory: when it last changed} for every package the bot has logs
    for, from the site's front page: one request instead of one listing per
    package (see unchanged). None if it can't be read, so every package is
    listed as before. A directory also changes when old logs are cleaned up,
    so a change doesn't mean a new attempt; no change means none."""
    try:
        page = http.get(f"{config.NIXPKGS_UPDATE_LOGS_URL}/", compressed=True)
    except (urllib.error.URLError, OSError) as e:
        print(f"  the log site's index: {e}; listing every package", file=sys.stderr)
        return None
    time.sleep(1)  # be polite
    found = {
        urllib.parse.unquote(name): datetime.strptime(when, "%d-%b-%Y %H:%M").replace(
            tzinfo=UTC
        )
        for name, when in DIRECTORY.findall(page or "")
    }
    if len(found) < MIN_DIRECTORIES:
        print(
            f"  the log site's index lists {len(found)} packages: not used",
            file=sys.stderr,
        )
        return None
    return found


def unchanged(attr, dates, since):
    """Whether the bot's logs for attr can't have changed since since (an ISO
    time, when they were last listed): its directory, by dates
    (directory_dates), last changed before then, or it has none (the bot has
    never tried). A minute's margin: the index only shows minutes."""
    if dates is None or not since:
        return False
    changed = dates.get(search_term(attr))
    return changed is None or changed < datetime.fromisoformat(since) - timedelta(
        minutes=1
    )


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


def diff_versions(log, was):
    """(from, to) from the diff of an updateScript log ("0 -> 1"), when every
    version change in it updates the version in `was` (wesnoth-devel-1.19.24)
    to the same new version; None otherwise (no diff, or the script failed
    before writing one)."""
    if not was or DIFF_HEAD not in log:
        return None
    diff = log.split(DIFF_HEAD, 1)[1].splitlines()
    removed = [
        line[1:] for line in diff if line.startswith("-") and not line.startswith("---")
    ]
    added = [
        line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")
    ]
    parts = was.split("-")
    candidates = ["-".join(parts[i:]) for i in range(1, len(parts))]
    found = set()
    for old in candidates:
        quoted = f'"{old}"'
        for minus in removed:
            if quoted not in minus:
                continue
            pattern = re.escape(minus).replace(re.escape(quoted), r'"([^"\n]+)"', 1)
            pattern = pattern.replace(re.escape(quoted), r'"\1"')
            for plus in added:
                if (match := re.fullmatch(pattern, plus)) and match.group(1) != old:
                    found.add((old, match.group(1)))
    return next(iter(found)) if len(found) == 1 else None


def parse(log):
    """{"outcome", "from"?, "to"?, "was"?, "pr"?, "excerpt"?} for one log.
    outcome: prOpened, prExists, cantUpdate (a newer version, but no way for
    the bot to update the package: excerpt says why), noChange, failed, or
    other. was: what
    nixpkgs had when the bot tried, as a version (2.7.3) or, with an
    updateScript, a name-version (wesnoth-devel-1.19.24)."""
    result = {}
    if info := UPDATE_INFO.search(log):
        result["from"], result["to"] = info.groups()
        if result["from"] != UPDATE_SCRIPT:
            result["was"] = result["from"]
    if "was" not in result and (package := UPDATE_SCRIPT_PACKAGE.search(log)):
        result["was"] = package.group(1)
    if result.get("from") == UPDATE_SCRIPT and (
        versions := diff_versions(log, result.get("was"))
    ):
        result["from"], result["to"] = versions
    prs = PR.findall(log)
    if PR_EXISTS in log:
        result["outcome"] = "prExists"
    elif prs:
        result["outcome"] = "prOpened"
    elif EMPTY_DIFF in log and result.get("from") not in (None, UPDATE_SCRIPT):
        result.update(outcome="cantUpdate", excerpt=REWRITER.findall(log))
    elif any(text in log for text in NO_CHANGE):
        result["outcome"] = "noChange"
    elif FAILED.search(log):
        result.update(outcome="failed", excerpt=excerpt(log))
    else:
        result["outcome"] = "other"
    if prs and result["outcome"] in ("prExists", "prOpened"):
        result["pr"] = int(prs[-1])
    return result


def latest_attempt(attr, known=None, same=False):
    """The bot's latest attempt at attr: {"attr", "date", "outcome", ...}, or
    None if it never tried. known: an attempt read before (the previous
    run's); if it's this same one, read with the same rules, its reading is
    taken (as_read) instead of downloading the log again. same: known is
    still the latest, as the logs haven't changed since it was read
    (unchanged): then nothing is asked at all."""
    if same:
        if known is None:
            return None  # it hadn't tried, and still hasn't
        if reused := as_read(known, attr, known.get("date")):
            return reused
    date = latest_date(attr)
    if date is None:
        return None
    reused = as_read(known, attr, date)
    if reused:
        return reused
    url = f"{attempts_url(attr)}{date}.log"
    log = http.get(url) or ""
    time.sleep(1)
    return {"attr": attr, "date": date, "log": url, "parser": PARSER, **parse(log)}


def as_read(known, attr, date):
    """known as its log read, if it's the attempt at attr on date, read by
    these rules (PARSER): without what add_attempts judged afterwards
    (superseded, ignored), which depends on the state of nixpkgs and the
    rules now, so it's judged again. A copy; None if it can't be reused."""
    if not known or known.get("parser") != PARSER:
        return None
    if known.get("attr") != attr or known.get("date") != date:
        return None
    if known.get("outcome") == "superseded" and not known.get("supersededOutcome"):
        return None  # can't tell what it was: read the log again
    attempt = {k: copy.deepcopy(v) for k, v in known.items() if k not in JUDGED}
    if known.get("outcome") == "superseded":
        attempt["outcome"] = known["supersededOutcome"]
    return attempt


def moved_on(attempt, version):
    """Whether version differs from what nixpkgs had when the bot tried.
    Unknown (False) when the log doesn't say what that was."""
    was = attempt.get("was")
    if not was or not version or was == UPDATE_SCRIPT:
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


# Outcomes that stop mattering once nixpkgs has moved past the version the
# bot tried.
SUPERSEDABLE = ("failed", "cantUpdate")


def supersede(attempt, where):
    """Mark attempt superseded, keeping what it was ("superseded" says
    "failed" or "couldn't update")."""
    attempt.update(
        supersededOutcome=attempt["outcome"], outcome="superseded", supersededOn=where
    )


def recheck_superseded(rows):
    """Mark failures superseded that are, now that more is known about master
    (an update PR merged there, found after the logs were read): so a row
    waiting for the channel doesn't also show as failed."""
    for row in rows:
        attempt = row.get("update")
        if not attempt or attempt.get("outcome") not in SUPERSEDABLE:
            continue
        where = superseded(attempt, row.get("nixVersion"), on_master(row))
        if where:
            supersede(attempt, where)
            row["updateFailure"] = False


def at_version(attempt, version):
    """Whether attempt is for version: its target ("to"), or, when an
    updateScript failed before picking one ("0 -> 1"), the version in "was"
    that nixpkgs had."""
    if not attempt or not version or version == UPDATE_SCRIPT_TO:
        return False
    if attempt.get("to") != UPDATE_SCRIPT_TO:
        return attempt.get("to") == version
    return bool(attempt.get("was")) and not moved_on(attempt, version)


def ignored(attempt, rules, outdated=False):
    """The reason a manual rule gives for ignoring a failed attempt, or None.
    rules: {version: reason}, the row's entry in package-lists/ignored-updates.nix.
    Matches the version the bot tried to update to ("to"), or, when an
    updateScript failed before picking one ("0 -> 1") and the package isn't
    outdated, the version nixpkgs had ("was")."""
    if attempt.get("outcome") != "failed" or not rules:
        return None
    if attempt.get("to") == UPDATE_SCRIPT_TO and outdated:
        return None
    for version, reason in rules.items():
        if at_version(attempt, version):
            return reason
    return None


def read_last_time(old):
    """Whether the last sync read the row's attempts (old: its row then):
    not if it couldn't (notRefreshed), nor if its turn hadn't come (unread,
    with every package)."""
    return (
        old is not None
        and "update" not in (old.get("notRefreshed") or {})
        and "update" not in (old.get("unread") or [])
    )


def to_read(row, attrs, old, dates, since):
    """Whether reading row's attempts takes a request: one of attrs has logs
    whose directory changed since the last sync read them (or that sync
    couldn't read them)."""
    known = (old or {}).get("update")
    refreshed = read_last_time(old)
    for attr in attrs:
        if dates is not None and search_term(attr) not in dates:
            continue  # no logs: nothing to read
        mine = known if (known or {}).get("attr") == attr else None
        if not (
            refreshed
            and unchanged(attr, dates, since)
            and (mine is not None or known is None)
        ):
            return True
    return False


def bulk_turns(rows, nixpkgs, before, dates, since, bulk):
    """With every package: the names of the rows in bulk (not on the lists,
    not pending) whose attempts are read this sync, at most
    UPDATE_LOGS_BUDGET of those that take a request (to_read): outdated or
    failing ones first, then those waiting longest (the rest keep their last
    attempt until a later sync). None of them when the log site's index
    can't be read (each would take a request)."""
    if dates is None:
        return set()
    waiting = []
    for row in rows:
        if row["name"] not in bulk or row.get("pending"):
            continue
        attrs = [a for a in row["attrs"] if a in nixpkgs]
        old = before.get(row["name"])
        if attrs and to_read(row, attrs, old, dates, since):
            urgent = is_outdated(row) or bool((old or {}).get("updateFailure"))
            read = ((old or {}).get("update") or {}).get("date") or ""
            waiting.append((not urgent, read, row["name"]))
    waiting.sort()
    return {name for _, _, name in waiting[: config.UPDATE_LOGS_BUDGET]}


def add_attempts(
    rows,
    nixpkgs,
    previous,
    now,
    ignored_updates=None,
    community=(),
    bulk=frozenset(),
):
    """Give every row in nixpkgs the bot's latest attempt ("update", None if
    it never tried) and whether that failed ("updateFailure"). With several
    attrs, the most recently attempted one counts. A row whose lookup fails
    keeps the previous run's result and is marked as not refreshed.
    ignored_updates: {row name: {version: reason}}, versions whose failed
    attempts count as superseded (a version that was never really released,
    say). community: the (row name, version) of those that are community
    rules (community.py), marked so on the attempt. bulk: with every
    package, the rows not on the lists: pending ones get no attempt at all,
    the others are read within a budget (bulk_turns); one whose turn hasn't
    come keeps its last attempt, and says it wasn't read ("unread":
    ["update"])."""
    ignored_updates = ignored_updates or {}
    print("Checking nixpkgs-update logs...", file=sys.stderr)
    before = {row["name"]: row for row in previous["packages"]}
    # When each package's logs last changed, in one request: those that
    # haven't since the last sync listed them aren't listed again.
    dates = directory_dates()
    since = previous.get("checkedAt")
    turns = bulk_turns(rows, nixpkgs, before, dates, since, bulk) if bulk else set()
    failed = consecutive = waited = 0
    for row in rows:
        attrs = [a for a in row["attrs"] if a in nixpkgs]
        if not attrs:
            continue  # not in nixpkgs: nothing for the bot to update
        if row["name"] in bulk:
            if row.get("pending"):
                continue  # generated sets: not read for now
            old = before.get(row["name"])
            if row["name"] not in turns and (
                dates is None or to_read(row, attrs, old, dates, since)
            ):
                waited += 1
                row["update"] = (old or {}).get("update")
                row["updateFailure"] = bool((old or {}).get("updateFailure"))
                row["unread"] = ["update"]
                continue
        down = consecutive >= config.UPDATE_LOGS_MAX_CONSECUTIVE_FAILURES
        try:
            if down:
                raise OSError("not asked: it didn't answer earlier lookups")
            old = before.get(row["name"])
            known = (old or {}).get("update")
            # Read fine last time: what it found still holds while the logs
            # haven't changed.
            refreshed = read_last_time(old)
            attempts = []
            for attr in attrs:
                if dates is not None and search_term(attr) not in dates:
                    continue  # no logs at all: the bot has never tried it
                mine = known if (known or {}).get("attr") == attr else None
                same = (
                    refreshed
                    and unchanged(attr, dates, since)
                    and (mine is not None or known is None)
                )
                if attempt := latest_attempt(attr, mine if same else known, same):
                    attempts.append(attempt)
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
            and attempt.get("from") == UPDATE_SCRIPT
            and "was" not in attempt
            and row.get("nixVersion")
        ):
            attempt["was"] = row["nixVersion"]
        # "master" comes from Hydra, read before this.
        where = (
            attempt
            and attempt["outcome"] in SUPERSEDABLE
            and superseded(attempt, row.get("nixVersion"), row.get("master"))
        )
        if where:
            supersede(attempt, where)
        elif attempt and (
            reason := ignored(
                attempt, ignored_updates.get(row["name"]), is_outdated(row)
            )
        ):
            supersede(attempt, "ignored")
            attempt["reason"] = reason
            if any(
                (row["name"], v) in community and at_version(attempt, v)
                for v in ignored_updates.get(row["name"]) or {}
            ):
                attempt["community"] = True
        for version in ignored_updates.get(row["name"]) or {}:
            # The community's own tidy-up lists those (community-check).
            if (row["name"], version) in community:
                continue
            if not at_version(attempt, version):
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
    if bulk:
        print(
            f"  {len(turns):,} packages not on the lists read (at most "
            f"{config.UPDATE_LOGS_BUDGET:,} a sync); {waited:,} not read",
            file=sys.stderr,
        )
