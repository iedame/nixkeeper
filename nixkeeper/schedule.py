"""Asking less about what's quiet. Something with nothing going on (a Hydra
build that went fine, a package with no open PRs or issues) is asked about
every QUIET_DAYS instead of daily: each on its own slot day, by a hash of its
name, so every day has about the same share (as nixpkgs-update spreads its
queue), or once that long has passed, in case a sync was missed. Whatever
has something going on is asked daily; each source decides what that is
(hydra.due, github.add_counts)."""

import zlib
from datetime import datetime, timedelta

from . import config

# The time of day a sync runs varies a little: what was checked a bit less
# than QUIET_DAYS ago counts as due.
SLACK = timedelta(hours=6)


def slot(name, when):
    """Whether when (a datetime) is name's day to be asked, while quiet: one
    day in QUIET_DAYS."""
    days = config.QUIET_DAYS
    return zlib.crc32(name.encode()) % days == when.date().toordinal() % days


def due(name, checked_at, now):
    """Whether something quiet, last checked at checked_at (ISO time, or
    None if never), is due now (ISO time): on its slot day, or once
    QUIET_DAYS have passed."""
    if not checked_at:
        return True
    when = datetime.fromisoformat(now)
    since = when - datetime.fromisoformat(checked_at)
    return since >= timedelta(days=config.QUIET_DAYS) - SLACK or slot(name, when)
