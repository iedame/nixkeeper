"""Mistakes in the package lists that would otherwise go unnoticed: a
maintainer handle no package lists (a typo tracks nothing, silently), an
extra package nixpkgs doesn't have, an update check or ignore rule for a
package that isn't tracked, a page theme the page doesn't have. Checked at
every sync, against the channel's package index it has loaded anyway; the
repository's `nix flake check` does the same before anything runs
(nix/package-lists.nix).

The sync prints them and writes them to the data ("listProblems"), and the
page shows them above the table."""

import sys

from . import follows, scale
from .tracking import by_pname, extra_attrs, extra_lists

# The page's palettes (page/logic.js PALETTES), for page.theme.
THEMES = ("classic", "catppuccin")


def page_settings(lists):
    """What the lists set for the page, for the data: {"theme": ...}, with
    only known values (problems() reports the others)."""
    theme = (lists.get("page") or {}).get("theme")
    return {"theme": theme} if theme in THEMES else {}


def problems(lists, nixpkgs, tracked):
    """What's wrong with lists, as sentences. tracked: the rows' names."""
    found = []
    handles = {
        (m.get("github") or "").lower()
        for p in nixpkgs.values()
        for m in p["meta"].get("maintainers") or []
        if isinstance(m, dict)
    }
    for handle in lists.get("maintainers") or []:
        if handle.lower() not in handles:
            found.append(
                f"maintainers: no package in nixos-unstable lists {handle} as a "
                "maintainer (a typo?)"
            )
    pnames = by_pname(nixpkgs)
    for list_name, entries in extra_lists(lists).items():
        for name in entries:
            if not extra_attrs(name, nixpkgs, pnames):
                found.append(
                    f"extraPackages.{list_name}: {name} is neither a nixpkgs "
                    "attribute nor a top-level pname (aliases like python3Packages "
                    "need their versioned name)"
                )
    for what, entries in (
        ("updateChecks", lists.get("updateChecks") or {}),
        ("ignoredUpdates", lists.get("ignoredUpdates") or {}),
    ):
        for name in sorted(set(entries) - set(tracked)):
            found.append(f"{what}: {name} isn't a tracked package")
    found += follows_problems(lists.get("updateChecks") or {}, tracked)
    big = scale.problem(len(tracked), lists)
    if big:
        found.append(big)
    most = lists.get("maxPackages")
    if most is not None and scale.limit(lists) != most:
        found.append(
            f"maxPackages: {most!r} isn't a positive whole number (using "
            f"{scale.MAX_PACKAGES:,})"
        )
    theme = (lists.get("page") or {}).get("theme")
    if theme is not None and theme not in THEMES:
        found.append(
            f"page.theme: {theme} isn't one of the page's themes ({', '.join(THEMES)})"
        )
    return found


def follows_problems(checks, tracked):
    """Update checks that follow a package (follows.py) that isn't tracked
    (where its versions and PRs would come from), themselves, or a package
    that follows another (no chains)."""
    found = []
    for name, target in sorted(follows.of(checks).items()):
        if name not in tracked:
            continue  # said above: the rule is for an untracked package
        if target == name:
            found.append(f"updateChecks.{name}: follows itself")
        elif target not in tracked:
            found.append(
                f"updateChecks.{name}: follows {target}, which isn't tracked "
                "(track it too: its versions and PRs are where this one's come from)"
            )
        elif target in follows.of(checks):
            found.append(
                f"updateChecks.{name}: follows {target}, which follows another "
                "package itself (follow that one instead)"
            )
    return found


def report(found):
    for problem in found:
        print(f"::warning::package lists: {problem}", file=sys.stderr)
