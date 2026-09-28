"""What changed since the previous run, for notifications."""

from . import config


def is_outdated(row):
    """Outdated per Repology, or per nixkeeper's own update check (a release
    Repology hasn't seen yet)."""
    return row.get("nixStatus") in config.OUTDATED_STATUSES or bool(
        (row.get("upstream") or {}).get("newer")
    )


def failed_builds(row):
    return [b for b in row.get("builds") or [] if b["status"] == "failed"]


def broken_builds(row):
    """Jobs nixpkgs marks broken: known failures, so not counted as failed."""
    return [b for b in row.get("builds") or [] if b["status"] == "broken"]


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
QUIET = ("caughtUp", "fixed", "broken", "refreshed", "added", "removed")

# What a source that couldn't be refreshed means for the row, for the issue.
STALE_LABELS = {
    "repology": "Repology lookup failed",
    "upstream": "nixkeeper's update check failing (package-lists/update-checks.nix)",
    "builds": "Hydra builds not refreshed",
    "update": "nixpkgs-update logs not refreshed",
}


def stale_sources(row):
    """Which of the row's sources couldn't be refreshed on its run."""
    sources = set(row.get("notRefreshed") or {})
    if row.get("staleSince"):
        sources.add("repology")
    return sources


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
        newly_broken = {build_label(row, b) for b in broken_builds(row)} - {
            build_label(old, b) for b in broken_builds(old)
        }
        if newly_broken:
            changes["broken"].append(row)
        # A failure nixpkgs now marks broken isn't fixed, just acknowledged.
        elif was_failing and not now_failing:
            changes["fixed"].append(row)
        if row.get("nixVulnerable") and not old.get("nixVulnerable"):
            changes["vulnerable"].append(row)
        # Per source: Hydra failing too, a day after an update check, is news.
        now_stale, was_stale = stale_sources(row), stale_sources(old)
        if now_stale - was_stale:
            changes["notRefreshed"].append(row)
        if was_stale - now_stale:
            changes["refreshed"].append(row)
    changes["removed"] = sorted(name for name in before if name not in names)
    return changes


def should_notify(changes):
    return any(changes[kind] for kind in NOTIFY)
