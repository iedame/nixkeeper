"""How big a sync is, and keeping it within reason: every tracked package
costs requests to public services (Repology, Hydra, the nixpkgs-update logs,
GitHub) and time. The sync says up front how long it should take; the list
check warns from WARN_PACKAGES packages; above MAX_PACKAGES the sync refuses
to start unless the lists raise the limit (maxPackages), so a big team or a
typo can't send thousands of requests by accident.

The costs are measured from nixkeeper's own daily runs: about 7 minutes for
47 packages, on GitHub Actions."""

import os
import sys

SECONDS_PER_PACKAGE = 7  # one request at a time, with a pause after each
REQUESTS_PER_PACKAGE = 8  # Repology 1-2, Hydra 3+, the bot's logs 2, GitHub
FIXED_SECONDS = 60  # the package index, the channel, GitHub's batches
WARN_PACKAGES = 500
MAX_PACKAGES = 2000


def estimate(count):
    """(seconds, requests) a sync of count packages takes, roughly."""
    return FIXED_SECONDS + count * SECONDS_PER_PACKAGE, count * REQUESTS_PER_PACKAGE


def duration(seconds):
    """ "about 7 min", "about 1 h 30 min": rounded, as estimates should be."""
    minutes = max(1, round(seconds / 60))
    if minutes < 50:
        return f"about {minutes} min"
    hours, minutes = divmod(round(minutes / 10) * 10, 60)
    return f"about {hours} h" + (f" {minutes} min" if minutes else "")


def describe(count):
    """count packages, and what syncing them costs, as a phrase."""
    seconds, requests = estimate(count)
    return (
        f"{count:,} packages: a sync takes {duration(seconds)} and makes about "
        f"{requests:,} requests to public services"
    )


def limit(lists):
    """The most packages the lists may track: their maxPackages if it's a
    positive whole number, else MAX_PACKAGES."""
    value = (lists or {}).get("maxPackages")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return MAX_PACKAGES


def check(lists, count):
    """Exit if count packages is over the lists' limit; otherwise say how long
    the sync should take (and, on GitHub Actions, in the run's summary)."""
    most = limit(lists)
    if count > most:
        sys.exit(
            f"The package lists track {describe(count)}, more than nixkeeper "
            f"syncs without being asked ({most:,}). To sync them anyway, set "
            f"maxPackages = {count}; in the lists (lists.maxPackages in the "
            "NixOS or nix-darwin module); or track fewer (smaller teams, "
            "shorter lists)."
        )
    message = f"Tracking {describe(count)}."
    print(message, file=sys.stderr)
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
