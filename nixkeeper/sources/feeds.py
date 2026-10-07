"""Sets' own sources of versions, which nixkeeper-versions reads daily
beside its Repology digest (https://github.com/iedame/nixkeeper-versions),
for the sets Repology mostly can't compare: Typst Universe
(typst_digest.py), the Emacs package archives (emacs_digest.py). Each is
one file next to the digest, loaded the same way (load), and compared with
its set's rows by its own rules, each such row then saying what it was
compared with ("feed", feed())."""

import gzip
import json
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from ..versions import version_key
from . import about, http

FORMAT = 1


def load(file, source, label, now):
    """The body of file (typst.json.gz, emacs.json.gz) beside the versions
    digest, or None (noting source's why, for the sources panel) when the
    digest is turned off, or the file isn't there, isn't current or can't be
    read: Repology's verdicts stay for its set. label names it in the log."""
    base = config.VERSIONS_DIGEST_URL
    if not base:
        return None
    try:
        body = http.get_bytes(base + file)
        if body is None:
            raise ValueError(f"no {file} yet")
        found = json.loads(gzip.decompress(body))
        if found.get("format") != FORMAT:
            raise ValueError(f"not in a format this nixkeeper reads ({base}{file})")
        at = found["fetchedAt"]
        age = datetime.fromisoformat(now) - datetime.fromisoformat(at)
        if age > timedelta(hours=config.VERSIONS_DIGEST_MAX_AGE_HOURS):
            about.note(source, False, "too old", at=at)
            print(
                f"::warning::{label}: not used, read {at}; Repology's stay",
                file=sys.stderr,
            )
            return None
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note(source, False, f"couldn't be read ({e})")
        print(
            f"::warning::{label}: couldn't use it ({e}); Repology's stay",
            file=sys.stderr,
        )
        return None
    return found


def compare(row, name, newest, url, released=None, dated=False, **more):
    """Make row outdated or newest against newest (a version on name's
    source, at url), and say so ("feed": what it was compared with, the
    day it was published when known; dated: versions are a build's date
    and time, as MELPA's; more: what else the source says)."""
    row["refVersion"] = newest
    row["feed"] = {
        "name": name,
        "version": newest,
        "url": url,
        **({"released": released} if released else {}),
        **({"dated": True} if dated else {}),
        **more,
    }
    row.pop("keptBeside", None)
    behind = version_key(newest) > version_key(row.get("nixVersion") or "")
    row["nixStatus"] = "outdated" if behind else "newest"
