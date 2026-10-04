"""How big a sync is, and keeping it within reason: every tracked package
costs requests to public services (Repology, Hydra, the nixpkgs-update logs,
GitHub) and time. The sync says up front how long it should take; the list
check warns from WARN_PACKAGES packages; above MAX_PACKAGES the sync refuses
to start unless the lists raise the limit (maxPackages), so a big team or a
typo can't send thousands of requests by accident.

The costs are measured from real syncs (71 packages, October 2026). A package
new to the data costs the most, the first time: everything is asked about.
After that, quiet ones are asked every few days (schedule.py), and a typical
day costs much less. Hydra, asked in the background, is the slowest source,
so it sets the time. To be checked against syncs of bigger lists."""

import os
import sys

# Per package: (seconds, requests).
FIRST = (4.2, 6)  # the first sync it's in: Repology by attribute, every job, every log
TYPICAL = (1.7, 1.6)  # a typical day after, with the quiet ones not asked
FIXED_SECONDS = 35  # the package index, the evaluations, GitHub's batches, ...
# Raised from 500 once quiet packages were asked every few days: a typical day
# for 1,500 now costs less than 500 did.
WARN_PACKAGES = 1500
# A safety net (a typo, a huge team), raised from 2,000 with the schedule.
MAX_PACKAGES = 5000
# GitHub Actions stops a job after 6 hours, publishing nothing: a sync that
# should take longer is warned about (check).
GITHUB_ACTIONS_SECONDS = 6 * 3600


def estimate(count, new=0):
    """(seconds, requests) a sync of count packages takes, roughly, new of
    them new to the data (asked about whole, the first time)."""
    new = min(new, count)
    known = count - new
    seconds = FIXED_SECONDS + known * TYPICAL[0] + new * FIRST[0]
    return seconds, round(known * TYPICAL[1] + new * FIRST[1])


def duration(seconds):
    """ "about 7 min", "about 1 h 30 min": rounded, as estimates should be."""
    minutes = max(1, round(seconds / 60))
    if minutes < 50:
        return f"about {minutes} min"
    hours, minutes = divmod(round(minutes / 10) * 10, 60)
    return f"about {hours} h" + (f" {minutes} min" if minutes else "")


def about(requests):
    """A number of requests, rounded as an estimate: 2,400, not 2,397."""
    return f"{round(requests, -2 if requests >= 1000 else -1):,}"


def describe(count):
    """count packages, and what syncing them costs, as a phrase: a typical
    day, and the first sync (all of them new)."""
    typical, first = estimate(count), estimate(count, count)
    return (
        f"{count:,} packages: a sync takes {duration(typical[0])} and makes about "
        f"{about(typical[1])} requests to public services on a typical day "
        f"({duration(first[0])} and {about(first[1])} the first time)"
    )


def limit(lists):
    """The most packages the lists may track: their maxPackages if it's a
    positive whole number, else MAX_PACKAGES."""
    value = (lists or {}).get("maxPackages")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return MAX_PACKAGES


def check(lists, count, new=0):
    """Exit if count packages is over the lists' limit; otherwise say how long
    this sync should take, new of them being new to the data (and, on GitHub
    Actions, in the run's summary, with a warning if it may outlast the job's
    6 hours)."""
    most = limit(lists)
    if count > most:
        sys.exit(
            f"The package lists track {describe(count)}, more than nixkeeper "
            f"syncs without being asked ({most:,}). To sync them anyway, set "
            f"maxPackages = {count}; in the lists (lists.maxPackages in the "
            "NixOS or nix-darwin module); or track fewer (smaller teams, "
            "shorter lists)."
        )
    seconds, requests = estimate(count, new)
    message = (
        f"Tracking {count:,} packages"
        + (f" ({new:,} new: asked about whole, the first time)" if new else "")
        + f": this sync should take {duration(seconds)} and make about "
        f"{about(requests)} requests to public services."
    )
    print(message, file=sys.stderr)
    if (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and seconds > GITHUB_ACTIONS_SECONDS * 0.9
    ):
        print(
            f"::warning::This sync may outlast GitHub Actions' 6-hour limit, and "
            f"publish nothing: {new:,} packages are new to the data. Add big "
            "lists in stages (only new packages cost this much), or run this "
            "first sync somewhere without the limit.",
            file=sys.stderr,
        )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"{message}\n\n")


def problem(count, lists):
    """The list check's sentence when count packages is a lot (from
    WARN_PACKAGES, up to the limit: over it, the sync refuses anyway), or
    None."""
    if count < WARN_PACKAGES or count > limit(lists):
        return None
    return (
        f"the lists track {describe(count)}: consider fewer (smaller teams, "
        "shorter lists), to go easy on those services"
    )
