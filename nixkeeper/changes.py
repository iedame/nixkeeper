"""What changed since the previous run, for notifications."""

from . import config


def is_outdated(row):
    return row.get("nixStatus") in config.OUTDATED_STATUSES


def failed_builds(row):
    return [b for b in row.get("builds") or [] if b["status"] == "failed"]


def build_label(row, build):
    """Which job failed: the platform, plus the attribute when the row has more
    than one (heroic / heroic-unwrapped)."""
    if build["attr"] == row["name"]:
        return build["system"]
    return f"{build['attr']} on {build['system']}"


def failures(row):
    """Why a row counts as failed (the page's red "failed" filter), if it does."""
    reasons = []
    if row.get("nixStatus") == "missing":
        reasons.append("not in nixpkgs")
    for build in failed_builds(row):
        reasons.append(f"build failure on {build_label(row, build)}")
    if row.get("updateFailure"):
        reasons.append("update failure reported")
    return reasons


# Changes that notify (posted as a comment), then ones only listed in the
# status issue: good news and bookkeeping shouldn't ping anyone.
NOTIFY = ("outdated", "failed", "vulnerable", "notRefreshed")
QUIET = ("caughtUp", "fixed", "added", "removed")


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
        # Per reason, so a second platform starting to fail is news too.
        now_failing, was_failing = set(failures(row)), set(failures(old))
        if now_failing - was_failing:
            changes["failed"].append(row)
        if was_failing and not now_failing:
            changes["fixed"].append(row)
        if row.get("nixVulnerable") and not old.get("nixVulnerable"):
            changes["vulnerable"].append(row)
        if row.get("staleSince") and not old.get("staleSince"):
            changes["notRefreshed"].append(row)
    changes["removed"] = sorted(name for name in before if name not in names)
    return changes


def should_notify(changes):
    return any(changes[kind] for kind in NOTIFY)
