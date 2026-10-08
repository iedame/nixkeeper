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
from . import http, updates_digest

LOG_NAME = re.compile(r'href="(\d{4}-\d{2}-\d{2})\.log"')
# The version of parse()'s rules, stored with each attempt ("parser"). A sync
# reuses the previous run's reading of a log it has already read (same
# attribute, same date) instead of downloading it again, but only one read
# with these same rules: bump this whenever parse() changes how it reads a
# log, so the next sync reads every log again and the change applies at once.
PARSER = 5
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
# Several already open for this update's branch (nixpkgs-update's GH.hs).
TOO_MANY_PRS = "Too many open PRs from "
# Every rewriter left the package as it was. After an updateScript attempt
# ("0 -> 1") that means there was nothing to update; after a real version
# ("1.37 -> 1.38"), that the bot has no way to update this package.
EMPTY_DIFF = "The diff was empty after rewrites"
# The same, said when the derivation's file came out unchanged (Update.hs).
NO_REWRITES = "No rewrites performed on derivation."
# Why the rewriters that could have applied didn't: "[version] generic
# version rewriter does not support multiple hashes".
REWRITER = re.compile(r"^\[(?:version|updateScript)\] (\S.*)$", re.MULTILINE)
NO_CHANGE = (
    EMPTY_DIFF,
    NO_REWRITES,
    "Package version did not change",
    # Someone updated it before the bot got to it.
    "not present in master derivation file",
)
# The bot already pushed this update to its branch (its PR open, or on its
# way): "An auto update branch exists with message `karakeep: 0.33.1 ->
# 0.33.2`. New version is 0.33.2." then this.
BRANCH_EXISTS = "An auto update branch exists with an equal or greater version"
BRANCH_MESSAGE = re.compile(
    r"An auto update branch exists with message `\S+ (\S+) -> (\S+)`"
)
# Nothing to update, and why: the candidate isn't newer by Nix's order ("0.1.0
# is not newer than 0.1.0-unstable-2024-06-14 according to Nix"), the
# rewriters found the same source, revision or dependencies' hash
# (Rewrite.hs, Update.hs), or the edit changes nothing nixpkgs builds.
NOTHING_NEWER = re.compile(
    r"^(?:\S+ is not newer than \S+ according to Nix.*"
    r"|(?:Hashes|cargo hashes|deps hashes|rev) equal; no update necessary.*"
    r"|Update edits cause no rebuilds\.)\s*$",
    re.MULTILINE,
)
# An updateScript package without a version: the bot can't tell what it
# updated to (Update.hs), so it can't update it.
NO_VERSION = re.compile(r"^The derivation has no 'version' attribute.*$", re.MULTILINE)
# The version rewriter changed the version but not where the source comes
# from: the bot can't update this package.
SOURCE_UNCHANGED = re.compile(r"^Source url did not change\.", re.MULTILINE)
# A request that failed, GitHub's API most often (opening the PR): the dump of
# the request is no excerpt, its host and answer are.
HTTP_ERROR = re.compile(r"^HTTPError \(HttpExceptionRequest", re.MULTILINE)
HTTP_HOST = re.compile(r'host\s*=\s*"([^"]+)"')
HTTP_STATUS = re.compile(r'statusCode = (\d+), statusMessage = "([^"]*)"')
HTTP_EXCEPTION = re.compile(
    r"\b(ConnectionTimeout|ResponseTimeout|ConnectionFailure|TooManyRedirects|"
    r"InternalException|ConnectionClosed)\b"
)
# The bot's own checks before it tries anything: a line right after one of
# these that no other rule reads is why it stopped there, on purpose (its
# skiplist: "Derivation file opts-out of auto-updates", "Do not update GNOME
# during a release cycle", "Python package with too many package rebuilds
# 3150 > 100", "rocm packages are upgraded in lockstep ...", "same as dune_3").
CHECKS = re.compile(
    r"^(?:attrpath: \S+|Checking auto update branch\.\.\."
    r"|No auto update branch exists)$"
)
# nix build errors, nixpkgs-update's own, and update script errors; and its
# checks of a build that went wrong (Nix.hs, Check.hs), which can end a log
# with no error line of nix's.
FAILED = re.compile(
    r"^error:|ExitFailure|failed with|^nix build failed\.|"
    r"nix log failed trying to get build logs|Could not find result link|"
    r"build succeeded unexpectedly|grep did not find version in file names|"
    r"Failed to read expected nix boolean",
    re.MULTILINE,
)
# Why a failed attempt failed ("failedBecause"): the first rule, in this
# order, that one of the log's lines meets, that line and the next ones its
# excerpt. Taken from ~200 failed attempts' logs (2026-10-07): a reason
# found earlier in the list is the cause of those found later (a missing
# dependency makes the build fail, a source gone makes nix-update fail).
# The bot's own machine failing, not the package (2026-10-08: 1,306 failed
# attempts said "the build users group 'nixbld' has no members"): first, as
# it explains whatever follows it. Still an update failure (someone should
# tell nixpkgs-update's maintainers), told apart by its reason.
BOT_FAILURE = (
    r"build users group '\S+' has no members"
    r"|cannot connect to socket at '\S*daemon-socket\S*'"
)
FAILED_BECAUSE = tuple(
    (because, re.compile(rule))
    for because, rule in (
        ("bot", BOT_FAILURE),
        # Not built where the bot builds: broken, insecure, not on x86_64-linux
        # (the package or a dependency).
        (
            "unavailable",
            r"Refusing to evaluate|is not available on the requested hostPlatform"
            r"|is marked as broken|not supported for interpreter",
        ),
        # nixpkgs' own changes to the source no longer apply: patches,
        # substituteInPlace.
        (
            "patch",
            r"Hunk #\d+ FAILED|patch does not apply|can't find file to patch"
            r"|Reversed \(or previously applied\) patch"
            r"|doesn't match anything in file"
            r"|substitute\(\): ERROR: file .* does not exist",
        ),
        # A dependency too old, missing, or new (a build backend, a module).
        (
            "dependency",
            r"not satisfied by version|^\s*- \S+ not installed$|Unmet dependencies"
            r"|Backend '\S+' is not available|Could NOT find"
            r"|required packages were not found|pkg-config tool not found"
            r"|Package '\S+'.* not found|Dependency \S+ found: NO|No module named"
            r"|no required module provides package|required \S+ module not found"
            r"|fatal error: \S+\.h: No such file",
        ),
        # A fixed-output hash (vendored dependencies, mostly) not updated, or
        # one the bot couldn't work out: it builds them with a wrong hash to
        # be told the right one, and they failed to build instead.
        (
            "hash",
            r"hash mismatch in fixed-output|ERROR: npmDepsHash|is out of date"
            r"|build succeeded unexpectedly",
        ),
        # The new version's source can't be fetched.
        (
            "source",
            r"curl: \(22\)|HTTP error 404|couldn't find remote ref|invalid refspec"
            r"|Unable to checkout|unable to download",
        ),
        # The package's updateScript (nix-update, mostly) failed on its own.
        (
            "updateScript",
            r"nix_update\.errors\.\w+:|update\.sh: line \d+:"
            r"|grep did not find version|does not provide attribute .*\.src'"
            r"|does not have a `passthru\.updateScript`|urllib\.error\.HTTPError:",
        ),
        (
            "tests",
            r"test result: FAILED|^Fail: +[1-9]|^=+ .*\d+ failed|^FAILED \S+::"
            r"|tests? failed out of|^--- FAIL:|^FAIL\s",
        ),
        # The build failed, and nix kept no log of it to tell why.
        ("noLog", r"build log of .* is not available"),
        # Any other error building it.
        (
            "build",
            r"error\[E\d+\]|fatal error:|: error:|error TS\d+|cannot find symbol"
            r"|[Cc]ompilation failed|undefined reference to|^CMake Error|^panic: "
            r"|^\S+: error: |^error: |\berror [A-Z]+\d+:|^ERROR[: ]|make: \*\*\*"
            r"|^\S+(?:Error|Exception|Invalid\w*): |cannot stat"
            r"|No such file or directory$"
            r"|but \.dist-info/METADATA specifies version",
        ),
    )
)
# nix's wrapping of a failed build: the reason comes before.
WRAPPING = re.compile(
    r"^error: (?:Cannot build|builder for|\d+ dependencies of derivation|build of)"
    r"|^\s*For full logs, run:"
)
# Lines no rule reads: that, and a lookup the bot makes of every Go
# package's source that fails harmlessly.
NOT_A_REASON = re.compile(
    rf"{WRAPPING.pattern}|in selection path '\S+\.originalSrc' not found"
)
# What the bot runs, not what it printed.
NOT_OUTPUT = ("Raw command:", "Standard output:")
UPDATE_SCRIPT_FAILED = "The update script for"
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


def meaningful_lines(log):
    """log's lines without colours, trailing spaces and blank lines."""
    return [
        line
        for line in (ANSI.sub("", raw).rstrip() for raw in log.splitlines())
        if line
    ]


def http_excerpt(log):
    """What a failed request was: ["HTTPError from api.github.com: 500
    Internal Server Error"], or the exception's name when there was no
    answer (a timeout)."""
    host = HTTP_HOST.search(log)
    status = HTTP_STATUS.search(log)
    exception = HTTP_EXCEPTION.search(log)
    what = (
        f"{status.group(1)} {status.group(2)}".strip()
        if status
        else exception.group(1)
        if exception
        else "no answer"
    )
    return [f"HTTPError from {host.group(1)}: {what}" if host else f"HTTPError: {what}"]


def output_lines(log):
    """What the builds and scripts printed in log: its meaningful lines,
    without the diff of the update, the rewriters' notes ("[version] ..."),
    the commands the bot ran, and the "> " nix puts before a build's lines."""
    lines, in_diff = [], False
    for raw in log.splitlines():
        line = ANSI.sub("", raw).rstrip()
        if line == DIFF_HEAD.strip():
            in_diff = True
            continue
        if in_diff:
            if not line or re.match(r"[ +\-@\\]|diff |index ", line):
                continue
            in_diff = False
        if not line.strip() or raw.startswith("@nix") or re.match(r"\[\w+\]", line):
            continue
        line = re.sub(r"^\s*> ?", "", line)
        if not line.startswith(NOT_OUTPUT):
            lines.append(line)
    return lines


def failed_because(log):
    """(why a failed attempt failed, its excerpt): the first of
    FAILED_BECAUSE's rules a line of log meets, and that line with the
    next; ("other", the last lines before nix's wrapping of the failure, or
    the log's last) when none does."""
    lines = output_lines(log)
    for because, rule in FAILED_BECAUSE:
        for i, line in enumerate(lines):
            if not NOT_A_REASON.search(line) and rule.search(line):
                return because, [
                    shown.strip()[:200] for shown in lines[i : i + EXCERPT_LINES]
                ]
    because = "updateScript" if UPDATE_SCRIPT_FAILED in log else "other"
    wrapped = next((i for i, line in enumerate(lines) if WRAPPING.search(line)), None)
    if wrapped:
        return because, [
            shown.strip()[:200]
            for shown in lines[max(0, wrapped - EXCERPT_LINES) : wrapped]
        ]
    return because, excerpt(log)


def skip_reason(log):
    """Why the bot stopped right after its own checks (CHECKS), on purpose:
    the line that came next, when it's the log's last; else None."""
    lines = meaningful_lines(log)
    if len(lines) >= 2 and CHECKS.match(lines[-2]) and not CHECKS.match(lines[-1]):
        return lines[-1][:200]
    return None


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
    """{"outcome", "from"?, "to"?, "was"?, "pr"?, "excerpt"?,
    "failedBecause"?} for one log.
    outcome: prOpened, prExists, branchExists (the bot already pushed this
    update to its branch), cantUpdate (a newer version, but no way for the
    bot to update the package: excerpt says why), noChange (excerpt: why,
    when the log says), skipped (the bot passed it over on purpose: excerpt
    says why), failed (failedBecause: why, see FAILED_BECAUSE; "request"
    when the bot's own request failed), or other. was: what
    nixpkgs had when the bot tried, as a version (2.7.3) or, with an
    updateScript, a name-version (wesnoth-devel-1.19.24)."""
    result = {}
    if info := UPDATE_INFO.search(log):
        result["from"], result["to"] = info.groups()
        if result["from"] != UPDATE_SCRIPT:
            result["was"] = result["from"]
        if "://" in result["to"]:
            # No new version, only where it would come from (ocamlPackages.
            # labltk's "8.06.16 -> https://github.com/...", 2026-10-03).
            del result["to"]
    if "was" not in result and (package := UPDATE_SCRIPT_PACKAGE.search(log)):
        result["was"] = package.group(1)
    if result.get("from") == UPDATE_SCRIPT and (
        versions := diff_versions(log, result.get("was"))
    ):
        result["from"], result["to"] = versions
    prs = PR.findall(log)
    # A version the bot tried, not an updateScript's run (0 -> 1).
    real_version = result.get("from") not in (None, UPDATE_SCRIPT)
    if PR_EXISTS in log or TOO_MANY_PRS in log:
        result["outcome"] = "prExists"
    elif prs:
        result["outcome"] = "prOpened"
    elif BRANCH_EXISTS in log:
        result["outcome"] = "branchExists"
        branch = BRANCH_MESSAGE.search(log)
        if branch and result.get("from") in (None, UPDATE_SCRIPT):
            result["from"], result["to"] = branch.groups()  # the script's versions
    elif HTTP_ERROR.search(log):
        # The bot's own request (to GitHub's API, mostly), not the package.
        result.update(
            outcome="failed", failedBecause="request", excerpt=http_excerpt(log)
        )
    elif (EMPTY_DIFF in log or NO_REWRITES in log) and real_version:
        result.update(outcome="cantUpdate", excerpt=REWRITER.findall(log))
    elif no_version := NO_VERSION.search(log):
        result.update(outcome="cantUpdate", excerpt=[no_version.group(0).strip()])
    elif unchanged := SOURCE_UNCHANGED.search(log):
        result.update(outcome="cantUpdate", excerpt=[unchanged.group(0)])
    elif any(text in log for text in NO_CHANGE):
        result["outcome"] = "noChange"
    elif nothing := NOTHING_NEWER.search(log):
        result.update(outcome="noChange", excerpt=[nothing.group(0).strip()])
    elif FAILED.search(log):
        because, lines = failed_because(log)
        result.update(outcome="failed", failedBecause=because, excerpt=lines)
    elif reason := skip_reason(log):
        result.update(outcome="skipped", excerpt=[reason])
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


BOT_FAILED = re.compile(BOT_FAILURE)


def with_bot_reason(attempt):
    """attempt, its reason "bot" when its log's excerpt says the bot's
    machine failed: for attempts read before that reason was (2026-10-08),
    by nixkeeper-updates or a log read earlier, without reading them again
    (the excerpt holds the error)."""
    if (
        attempt
        and attempt.get("outcome") == "failed"
        and attempt.get("failedBecause") != "bot"
        and BOT_FAILED.search("\n".join(attempt.get("excerpt") or []))
    ):
        attempt["failedBecause"] = "bot"
    return attempt


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


def read_attempts(attrs, old, dates, since, digest=None):
    """The bot's latest attempt at each of attrs it has tried, and how many
    came from the digest: from it where it can say (updates_digest.attempt),
    else from the logs, reusing the last sync's reading (old: its row) of a
    log that hasn't changed since (since; dates: directory_dates). Raises
    when the logs can't be read."""
    known = (old or {}).get("update")
    # Read fine last time: what it found still holds while the logs haven't
    # changed.
    refreshed = read_last_time(old)
    attempts, taken = [], 0
    for attr in attrs:
        if digest is not None:
            entry = digest.get(search_term(attr))
            if entry is None:
                continue  # the bot has never tried it
            if found := updates_digest.attempt(entry, attr, PARSER):
                attempts.append(found)
                taken += 1
                continue  # else read it: an attempt the digest hasn't
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
    return attempts, taken


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
    not of a set updated in bulk) whose attempts are read this sync, at most
    UPDATE_LOGS_BUDGET of those that take a request (to_read): outdated or
    failing ones first, then those waiting longest (the rest keep their last
    attempt until a later sync). None of them when the log site's index
    can't be read (each would take a request)."""
    if dates is None:
        return set()
    waiting = []
    for row in rows:
        if row["name"] not in bulk or row.get("set"):
            continue
        attrs = [a for a in row["attrs"] if a in nixpkgs]
        old = before.get(row["name"])
        if attrs and to_read(row, attrs, old, dates, since):
            urgent = is_outdated(row) or bool((old or {}).get("updateFailure"))
            read = ((old or {}).get("update") or {}).get("date") or ""
            waiting.append((not urgent, read, row["name"]))
    waiting.sort()
    return {name for _, _, name in waiting[: config.UPDATE_LOGS_BUDGET]}


def add_queue(rows, nixpkgs, queue):
    """Give each row the bot will try again ("queued": {"by": the day
    expected, "candidates": [[version, source URL], ...]}) from its queue
    (updates_digest.load_queue): its soonest attribute's, and the versions
    the bot would update it to that nixpkgs doesn't have yet. Rows not in
    nixpkgs or not in the queue get none; nothing at all without a queue."""
    if not queue:
        return
    for row in rows:
        found = [
            queue[search_term(a)]
            for a in row.get("attrs") or []
            if a in nixpkgs and search_term(a) in queue
        ]
        if not found:
            continue
        soonest = min(found, key=lambda e: e["by"])
        candidates = []
        for candidate in soonest["candidates"]:
            # [from, to, source URL]; the URL "" when the queue had none.
            to, source = candidate[1], (candidate[2:] or [""])[0]
            if to != row.get("nixVersion") and [to, source] not in candidates:
                candidates.append([to, source])
        row["queued"] = {"by": soonest["by"]}
        if candidates:
            row["queued"]["candidates"] = candidates
        if soonest.get("script"):
            # It also runs the package's updateScript, which decides the version.
            row["queued"]["script"] = True


def add_attempts(
    rows,
    nixpkgs,
    previous,
    now,
    ignored_updates=None,
    community=(),
    bulk=frozenset(),
    digest=None,
):
    """Give every row in nixpkgs the bot's latest attempt ("update", None if
    it never tried) and whether that failed ("updateFailure"). With several
    attrs, the most recently attempted one counts. A row whose lookup fails
    keeps the previous run's result and is marked as not refreshed.
    ignored_updates: {row name: {version: reason}}, versions whose failed
    attempts count as superseded (a version that was never really released,
    say). community: the (row name, version) of those that are community
    rules (community.py), marked so on the attempt. digest: nixkeeper-
    updates' (updates_digest.load), the attempts it can answer taken from
    it instead of the logs. bulk: with every package, the rows not on the
    lists: the digest's last read attempt (without one, they're read within
    a budget: bulk_turns, but not those of sets updated in bulk, which the
    bot rarely tries); one with none says it wasn't read ("unread":
    ["update"])."""
    ignored_updates = ignored_updates or {}
    print("Checking nixpkgs-update logs...", file=sys.stderr)
    before = {row["name"]: row for row in previous["packages"]}
    # When each package's logs last changed, in one request: those that
    # haven't since the last sync listed them aren't listed again.
    dates = directory_dates()
    since = previous.get("checkedAt")
    turns = (
        bulk_turns(rows, nixpkgs, before, dates, since, bulk)
        if bulk and digest is None
        else set()
    )
    failed = consecutive = waited = from_digest = 0
    for row in rows:
        attrs = [a for a in row["attrs"] if a in nixpkgs]
        if not attrs:
            continue  # not in nixpkgs: nothing for the bot to update
        attempts = None
        if row["name"] in bulk:
            if row.get("set") and digest is None:
                continue  # sets updated in bulk: the digest's attempts only
            old = before.get(row["name"])
            if digest is not None:
                # The digest's last read attempts, whatever it hasn't read yet.
                entries = [(a, digest.get(search_term(a))) for a in attrs]
                attempts = [
                    found
                    for a, entry in entries
                    if entry and (found := updates_digest.known(entry, a))
                ]
                from_digest += bool(attempts)
                if not attempts and any(entry for _, entry in entries):
                    waited += 1
                    row["unread"] = ["update"]
            elif row["name"] not in turns and (
                dates is None or to_read(row, attrs, old, dates, since)
            ):
                waited += 1
                row["update"] = with_bot_reason((old or {}).get("update"))
                row["updateFailure"] = bool((old or {}).get("updateFailure"))
                row["unread"] = ["update"]
                continue
        if attempts is None:
            down = consecutive >= config.UPDATE_LOGS_MAX_CONSECUTIVE_FAILURES
            try:
                if down:
                    raise OSError("not asked: it didn't answer earlier lookups")
                attempts, taken = read_attempts(
                    attrs, before.get(row["name"]), dates, since, digest
                )
                from_digest += taken
                consecutive = 0
            except (urllib.error.URLError, OSError) as e:
                failed += 1
                consecutive += not down
                if not down:
                    print(f"  {row['name']}: {e}", file=sys.stderr)
                old = before.get(row["name"], {})
                row["update"] = with_bot_reason(old.get("update"))
                row["updateFailure"] = bool(old.get("updateFailure"))
                history.not_refreshed(
                    row,
                    "update",
                    f"couldn't read the nixpkgs-update logs ({e})",
                    old,
                    now,
                )
                continue
        attempt = with_bot_reason(max(attempts, key=lambda a: a["date"], default=None))
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
    if digest is not None:
        print(
            f"  {from_digest:,} attempts from the updates digest"
            + (f"; {waited:,} packages not read yet there" if waited else ""),
            file=sys.stderr,
        )
    elif bulk:
        print(
            f"  {len(turns):,} packages not on the lists read (at most "
            f"{config.UPDATE_LOGS_BUDGET:,} a sync); {waited:,} not read",
            file=sys.stderr,
        )
