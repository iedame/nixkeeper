"""Stackage LTS, from nixkeeper-versions' stackage.json.gz (feeds.py): nixpkgs
pins about 3,400 of its haskellPackages to a Stackage LTS series
(configuration-hackage2nix/stackage.yaml), so for those the version to be
at is the newest of that series, not Hackage's newest, which Stackage
holds back until its next series. The daily sync compares those rows with
it instead of Repology (which knows only Hackage's newest): outdated when
behind the series' newest snapshot (nixpkgs moves to it with the next
haskell-updates merge), newest when at it, whatever Hackage has. The rest
of haskellPackages keep Repology's verdict (Hackage's newest)."""

import sys

from ..versions import version_key
from . import about, feeds

FILE = "stackage.json.gz"
PREFIX = "haskellPackages."
PACKAGE_URL = "https://www.stackage.org/{snapshot}/package/{name}"


def load(now):
    """{"series", "nixpkgs", "snapshot", "versions"} (stackage.json.gz's), or
    None (saying why) when it can't be used (feeds.load): Repology's
    verdicts stay."""
    found = feeds.load(FILE, "stackage", "Stackage LTS", now)
    if found is None:
        return None
    print(
        f"Stackage: nixpkgs follows {found['nixpkgs']}, {found['snapshot']} is the "
        f"newest; {len(found['versions']):,} packages, read {found['fetchedAt']}",
        file=sys.stderr,
    )
    about.note(
        "stackage",
        True,
        at=found["fetchedAt"],
        snapshot=found["snapshot"],
        nixpkgs=found["nixpkgs"],
        packages=len(found["versions"]),
    )
    return found


def series_name(series):
    """lts-24: "Stackage LTS 24"."""
    return "Stackage " + series.replace("lts-", "LTS ")


def apply(rows, nixpkgs, found):
    """Compare the rows of the haskellPackages nixpkgs pins (found: load's)
    with their version in the series' newest snapshot: outdated or newest,
    saying so ("feed", with which snapshot nixpkgs follows, and Hackage's
    newer version when Stackage holds the package back: "heldBack")."""
    if not found:
        return
    versions = found.get("versions") or {}
    for row in rows:
        attrs = row.get("attrs") or []
        if not attrs or not all(a.startswith(PREFIX) for a in attrs):
            continue
        name = attrs[0][len(PREFIX) :]
        version = versions.get(name)
        if not version or not row.get("nixVersion"):
            continue
        # Repology's newest: Hackage's, when it's past what the series has.
        hackage = row.get("refVersion")
        held = hackage and version_key(hackage) > version_key(version)
        feeds.compare(
            row,
            series_name(found["series"]),
            version,
            PACKAGE_URL.format(snapshot=found["snapshot"], name=name),
            snapshot=found["snapshot"],
            followed=found["nixpkgs"],
            **({"heldBack": hackage} if held else {}),
        )
