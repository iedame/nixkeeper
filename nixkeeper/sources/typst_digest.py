"""Typst Universe's newest versions, from nixkeeper-versions' typst.json.gz
(https://github.com/iedame/nixkeeper-versions): the source of nixpkgs'
typstPackages, which Repology mostly can't compare (it sees nixpkgs alone,
"unique", or the versions nixpkgs keeps, "legacy"). The daily sync compares
typstPackages' rows with it instead (apply): a package's latest attribute
(typstPackages.cetz) against Universe's newest version, the versioned ones
(typstPackages.cetz_0_3_0) as older versions kept beside it."""

import gzip
import json
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from ..versions import version_key
from . import about, http

FORMAT = 1
FILE = "typst.json.gz"
PREFIX = "typstPackages."
NAME = "Typst Universe"
PACKAGE_URL = "https://typst.app/universe/package/{}"


def load(now):
    """{name: {"version", "released"?}} for every package on Typst Universe,
    or None (saying why) when the versions digest is turned off, or the file
    isn't there, isn't current or can't be read: Repology's verdicts stay."""
    base = config.VERSIONS_DIGEST_URL
    if not base:
        return None
    try:
        body = http.get_bytes(base + FILE)
        if body is None:
            raise ValueError(f"no {FILE} yet")
        found = json.loads(gzip.decompress(body))
        if found.get("format") != FORMAT:
            raise ValueError(f"not in a format this nixkeeper reads ({base}{FILE})")
        at = found["fetchedAt"]
        age = datetime.fromisoformat(now) - datetime.fromisoformat(at)
        if age > timedelta(hours=config.VERSIONS_DIGEST_MAX_AGE_HOURS):
            about.note("typst", False, "too old", at=at)
            print(
                f"::warning::Typst Universe's versions: not used, read {at}; "
                "Repology's stay",
                file=sys.stderr,
            )
            return None
        packages = found["packages"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note("typst", False, f"couldn't be read ({e})")
        print(
            f"::warning::Typst Universe's versions: couldn't use them ({e}); "
            "Repology's stay",
            file=sys.stderr,
        )
        return None
    print(f"Typst Universe: {len(packages):,} packages, read {at}", file=sys.stderr)
    about.note("typst", True, at=at, packages=len(packages))
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
        newest = found["version"]
        row["refVersion"] = newest
        row["feed"] = {
            "name": NAME,
            "version": newest,
            "url": PACKAGE_URL.format(name),
            **({"released": found["released"]} if found.get("released") else {}),
        }
        latest = PREFIX + name
        latest_version = (nixpkgs.get(latest) or {}).get("version")
        if latest not in attrs and latest_version and latest_version != version:
            row["nixStatus"] = config.KEPT
            row["keptBeside"] = {"attr": latest, "version": latest_version}
            continue
        row.pop("keptBeside", None)
        row["nixStatus"] = (
            "outdated" if version_key(newest) > version_key(version) else "newest"
        )
