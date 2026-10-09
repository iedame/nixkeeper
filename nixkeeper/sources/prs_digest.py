"""nixkeeper-prs' digest (https://github.com/iedame/nixkeeper-prs): every
open PR and issue of nixpkgs, and the PRs merged into master since the
nixos-unstable channel's commit, as its hourly workflow lists them. The
daily sync counts each package's open PRs and issues, and finds its open
and merged update PRs, in these lists (github_bulk) instead of listing
them itself.

Each list is used while it was made recently (PRS_DIGEST_MAX_AGE_HOURS),
and the merged PRs only when they were listed since the very channel
commit the sync reads (a newer channel would count PRs it has as not in
it yet): else the sync lists them itself, as it did before the digest."""

import json
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from . import about, http

FORMAT = 1
PR_URL = "https://github.com/NixOS/nixpkgs/pull/"


def recent(at, now):
    """Whether a list made at (ISO) is recent enough to use."""
    if not at:
        return False
    age = datetime.fromisoformat(now) - datetime.fromisoformat(at)
    return age <= timedelta(hours=config.PRS_DIGEST_MAX_AGE_HOURS)


def node(pr):
    """A PR as github_bulk's listings have it (GraphQL's names)."""
    return {
        "number": pr["n"],
        "title": pr["title"],
        "url": PR_URL + str(pr["n"]),
        "isDraft": pr.get("draft", False),
        "baseRefName": pr.get("base"),
    }


def _list(base, name, key):
    """A list of the digest (name: its file), as written: its key's items."""
    data = json.loads(http.get(base + name, compressed=True) or "null")
    if not data or data.get("format") != FORMAT:
        raise ValueError(f"no {name} in a format this nixkeeper reads")
    return data.get(key) or []


def load(now, revision):
    """{"open": (PRs, issues) or None, "merged": PRs or None}, as
    github_bulk's listings give them (each None when it's not recent, or
    merged when listed since another channel commit than revision), or None
    (saying why) when it's turned off or can't be read."""
    base = config.PRS_DIGEST_URL
    if not base:
        return None
    try:
        meta = json.loads(http.get(base + "meta.json") or "null")
        if not meta or meta.get("format") != FORMAT:
            raise ValueError(f"no digest in a format this nixkeeper reads ({base})")
        issues_meta = meta.get("issues") or {}
        merged_meta = meta.get("merged") or {}
        found = {"open": None, "merged": None}
        why = []
        if recent(meta.get("generatedAt"), now) and recent(issues_meta.get("at"), now):
            prs = [node(p) for p in _list(base, "prs.json", "prs")]
            issues = [
                {"number": i["n"], "title": i["title"]}
                for i in _list(base, "issues.json", "issues")
            ]
            found["open"] = (prs, issues)
        else:
            why.append("open PRs and issues too old")
        if merged_meta.get("revision") != revision:
            why.append("merged PRs since another channel commit")
        elif not recent(merged_meta.get("at"), now):
            why.append("merged PRs too old")
        else:
            found["merged"] = [
                node(p) for p in _list(base, "merged.json", "prs") if p.get("n")
            ]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note("prs", False, f"couldn't be read ({e})")
        print(
            f"::warning::PRs digest: couldn't use it ({e}); listing them here",
            file=sys.stderr,
        )
        return None
    used = found["open"] is not None or found["merged"] is not None
    about.note(
        "prs",
        used,
        "; ".join(why) if not used else None,
        at=meta.get("generatedAt"),
        prs=len(found["open"][0]) if found["open"] else None,
        issues=len(found["open"][1]) if found["open"] else None,
        merged=len(found["merged"]) if found["merged"] is not None else None,
        partly="; ".join(why) if used and why else None,
    )
    print(
        f"PRs digest: made {meta.get('generatedAt')}"
        + (
            f", {len(found['open'][0]):,} open PRs, {len(found['open'][1]):,} issues"
            if found["open"]
            else ""
        )
        + (
            f", {len(found['merged']):,} merged since the channel"
            if found["merged"] is not None
            else ""
        )
        + (f" ({'; '.join(why)}: listed here)" if why else ""),
        file=sys.stderr,
    )
    return found
