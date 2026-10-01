"""Mistakes in the package lists that would otherwise go unnoticed: a
maintainer handle no package lists (a typo tracks nothing, silently), an
extra package nixpkgs doesn't have, an update check or ignore rule for a
package that isn't tracked. Checked at every sync, against the channel's
package index it has loaded anyway; the repository's `nix flake check` does
the same before anything runs (nix/package-lists.nix).

The sync prints them and writes them to the data ("listProblems"), and the
page shows them above the table."""

import sys

from .tracking import by_pname, extra_attrs, extra_lists


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
    return found


def report(found):
    for problem in found:
        print(f"::warning::package lists: {problem}", file=sys.stderr)
