"""What changed since the previous run, for notifications."""
from . import config


def is_outdated(row):
    return row.get("nixStatus") in config.OUTDATED_STATUSES


def failures(row):
    """Why a row counts as failed (the page's red "failed" filter), if it does."""
    reasons = []
    if row.get("nixStatus") == "missing":
        reasons.append("not in nixpkgs")
    if row.get("buildFailure"):
        reasons.append("build failure reported")
    if row.get("updateFailure"):
        reasons.append("update failure reported")
    return reasons


# Changes that notify (posted as a comment), then ones only listed in the
# status issue: good news and bookkeeping shouldn't ping anyone.
NOTIFY = ("outdated", "failed", "vulnerable", "notRefreshed")
QUIET = ("caughtUp", "added", "removed")


def diff(previous, rows):
    """Rows (or names, for removed) per kind of change. Packages new to
    tracking only count as added: the first run, or a newly listed package that
    is already outdated, isn't news."""
    before = {row["name"]: row for row in previous["packages"]}
    names = {row["name"] for row in rows}
    changes = {kind: [] for kind in NOTIFY + QUIET}
    for row in rows:
        old = before.get(row["name"])
        if old is None:
            changes["added"].append(row)
            continue
        if is_outdated(row) and not is_outdated(old):
            changes["outdated"].append(row)
        if is_outdated(old) and not is_outdated(row):
            changes["caughtUp"].append(row)
        if failures(row) and not failures(old):
            changes["failed"].append(row)
        if row.get("nixVulnerable") and not old.get("nixVulnerable"):
            changes["vulnerable"].append(row)
        if row.get("staleSince") and not old.get("staleSince"):
            changes["notRefreshed"].append(row)
    changes["removed"] = sorted(name for name in before if name not in names)
    return changes


def should_notify(changes):
    return any(changes[kind] for kind in NOTIFY)
