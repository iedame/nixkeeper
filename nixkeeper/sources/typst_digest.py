"""Typst Universe's newest versions, from nixkeeper-versions' typst.json.gz
(feeds.py): the source of nixpkgs' typstPackages, which Repology mostly
can't compare (it sees nixpkgs alone, "unique", or the versions nixpkgs
keeps, "legacy"). The daily sync compares typstPackages' rows with it
instead (apply): a package's latest attribute (typstPackages.cetz) against
Universe's newest version, the versioned ones (typstPackages.cetz_0_3_0)
as older versions kept beside it."""

import sys

from .. import config
from . import about, feeds

FILE = "typst.json.gz"
PREFIX = "typstPackages."
NAME = "Typst Universe"
PACKAGE_URL = "https://typst.app/universe/package/{}"


def load(now):
    """{name: {"version", "released"?}} for every package on Typst Universe,
    or None (saying why) when it can't be used (feeds.load): Repology's
    verdicts stay."""
    found = feeds.load(FILE, "typst", "Typst Universe's versions", now)
    if found is None:
        return None
    packages = found.get("packages") or {}
    print(
        f"Typst Universe: {len(packages):,} packages, read {found['fetchedAt']}",
        file=sys.stderr,
    )
    about.note("typst", True, at=found["fetchedAt"], packages=len(packages))
    return packages


def apply(rows, nixpkgs, packages):
    """Compare typstPackages' rows with Typst Universe (packages: load's):
    the row of a package's latest attribute (typstPackages.cetz) is newest
    or outdated against Universe's newest version; a versioned one
    (typstPackages.cetz_0_3_0) is an older version kept beside it, unless
    it's the same version (a row of its own when Repology doesn't list
    the package): then it's compared too. Each says so ("feed": what it was
    compared with). Packages Universe doesn't have keep Repology's."""
    if not packages:
        return
    for row in rows:
        attrs = row.get("attrs") or []
        if not attrs or not all(a.startswith(PREFIX) for a in attrs):
            continue
        pkg = next((nixpkgs[a] for a in attrs if a in nixpkgs), None)
        name = (pkg or {}).get("pname")
        found = packages.get(name) if name else None
        version = row.get("nixVersion")
        if not found or not version:
            continue
        latest = PREFIX + name
        latest_version = (nixpkgs.get(latest) or {}).get("version")
        if latest not in attrs and latest_version and latest_version != version:
            row["refVersion"] = found["version"]
            row["feed"] = {
                "name": NAME,
                "version": found["version"],
                "url": PACKAGE_URL.format(name),
                **({"released": found["released"]} if found.get("released") else {}),
            }
            row["nixStatus"] = config.KEPT
            row["keptBeside"] = {"attr": latest, "version": latest_version}
            continue
        feeds.compare(
            row,
            NAME,
            found["version"],
            PACKAGE_URL.format(name),
            released=found.get("released"),
        )
