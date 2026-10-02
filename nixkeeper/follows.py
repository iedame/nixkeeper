"""Packages updated together with another, to the same version, by the same
PRs (msedgedriver with microsoft-edge): an update check that says so,

    msedgedriver = { follows = "microsoft-edge"; };

instead of looking anywhere itself. The follower then counts the package it
follows' newest version as its own (recorded like an update check's result,
row["upstream"] with "follows"), and its update PRs, merged and open, as its
own: their titles name only that package, so a search by the follower's name
can't find them.

The package followed must be tracked too (its row is where all that comes
from), and can't follow another itself. The rule is recorded on the row, so
the hourly checks follow along without reading the lists."""

from .sources import upstream

PR_FIELDS = ("openPR", "masterPR")


def of(checks):
    """{follower: followed} from update checks."""
    return {
        name: check["follows"]
        for name, check in checks.items()
        if isinstance(check, dict) and isinstance(check.get("follows"), str)
    }


def recorded(rows):
    """{follower: followed} as the rows say, from the last sync."""
    return {
        row["name"]: row["upstream"]["follows"]
        for row in rows
        if (row.get("upstream") or {}).get("follows")
    }


def pairs(rows, follows):
    """(follower row, followed row) for each rule both of whose packages are
    tracked; not for a package that follows another follower (no chains)."""
    by_name = {row["name"]: row for row in rows}
    for name, target in sorted(follows.items()):
        row, other = by_name.get(name), by_name.get(target)
        if row and other and target not in follows and target != name:
            yield row, other


def apply_versions(rows, follows, now, community=frozenset()):
    """Give each follower the newest version of the package it follows (its
    refVersion, once master is counted), as an update check would. Returns
    the followers it changed."""
    changed = []
    for row, other in pairs(rows, follows):
        version = other.get("refVersion") or other.get("nixVersion")
        if not version:
            continue
        found = {"version": version, "checkedAt": now, "follows": other["name"]}
        if row["name"] in community:
            found["community"] = True
        upstream.apply(row, found)
        changed.append(row)
    return changed


def apply_prs(rows, follows):
    """Give each follower the update PRs of the package it follows, where it
    has them (the same PRs update both)."""
    for row, other in pairs(rows, follows):
        for field in PR_FIELDS:
            if other.get(field):
                row[field] = other[field]
