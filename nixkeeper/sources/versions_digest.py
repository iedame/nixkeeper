"""nixkeeper-versions' digest of Repology (https://github.com/iedame/nixkeeper-
versions): every nixpkgs project's packages in every repository, read in
bulk the way nixpkgs-update reads Repology, refreshed daily for outdated
projects and weekly for the rest. The daily sync takes tracked packages'
projects from it instead of looking each up on Repology (lookup.py), and
still asks Repology for those it can't answer: missing from it (new in
nixpkgs), or with another version than the channel's (changed since), and
for all of them when the digest isn't current or can't be read."""

import gzip
import io
import json
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from . import http

FORMAT = 1


def current(meta, now):
    """Whether the digest is recent enough: its outdated projects were read
    within VERSIONS_DIGEST_MAX_AGE_HOURS (the workflow runs daily)."""
    age = datetime.fromisoformat(now) - datetime.fromisoformat(meta["outdatedAt"])
    return age <= timedelta(hours=config.VERSIONS_DIGEST_MAX_AGE_HOURS)


def projects_of(lines, attrs):
    """{attr: (project, entries, checked day)} for the attrs among a digest's
    lines (one project each) whose nixpkgs packages they are; only those
    projects are kept, so memory stays small (the whole digest is about
    2 million entries)."""
    found = {}
    for line in lines:
        project = json.loads(line)
        for entry in project["entries"]:
            attr = entry.get("srcname")
            if entry["repo"] == config.NIX_REPO and attr in attrs:
                found[attr] = (
                    project["project"],
                    project["entries"],
                    project["checked"],
                )
    return found


def load(attrs, now):
    """{attr: (project, entries, checked day)} for the tracked attrs the
    digest has, or None (saying why) when it's turned off, not current or
    can't be read."""
    base = config.VERSIONS_DIGEST_URL
    if not base:
        return None
    try:
        meta = json.loads(http.get(base + "meta.json") or "null")
        if not meta or meta.get("format") != FORMAT:
            raise ValueError(f"no digest in a format this nixkeeper reads ({base})")
        if not current(meta, now):
            print(
                f"::warning::Versions digest: not used, its outdated projects are "
                f"from {meta['outdatedAt']}; looking packages up on Repology",
                file=sys.stderr,
            )
            return None
        body = http.get_bytes(base + "projects.jsonl.gz")
        if body is None:
            raise ValueError("its projects.jsonl.gz is missing")
        with gzip.open(io.BytesIO(body), "rt") as lines:
            found = projects_of(lines, set(attrs))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(
            f"::warning::Versions digest: couldn't use it ({e}); looking packages "
            "up on Repology",
            file=sys.stderr,
        )
        return None
    print(
        f"Versions digest: {meta['projects']:,} projects, outdated ones read "
        f"{meta['outdatedAt']}; {len(found):,} of {len(set(attrs)):,} tracked "
        "attributes in it",
        file=sys.stderr,
    )
    return found


def answer(digest, attrs, nixpkgs):
    """(project, entries, checked day) for a tracked package (its attrs) from
    the digest, or None when Repology must be asked: none of its attrs is in
    the digest, or one is with another version than the channel's (nixpkgs
    changed it since the digest was read, or Repology hasn't caught up)."""
    found = None
    for attr in attrs:
        if attr not in digest:
            continue
        project, entries, checked = digest[attr]
        nix = [
            e
            for e in entries
            if e["repo"] == config.NIX_REPO and e.get("srcname") == attr
        ]
        channel = (nixpkgs.get(attr) or {}).get("version")
        if channel and all(e.get("version") != channel for e in nix):
            return None
        found = found or (project, entries, checked)
    return found
