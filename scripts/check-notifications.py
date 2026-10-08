"""On a pull request that changes notifications/: the names its files use
are nixpkgs' today, and nobody is added but the pull request's author. Run
by .github/workflows/ci.yml:

    python3 scripts/check-notifications.py BASE_SHA AUTHOR

- Names: each maintainer and mentioned handle is a GitHub handle in
  nixos-unstable's maintainers, each team a team's shortName there. Checked
  against nixos-unstable itself (fetched once, only when a file changed),
  not this flake's nixpkgs, which lags it: a new maintainer or team would
  fail until the lock moves. nix flake check (nix/notifications.nix) has
  the rest of the format.
- Consent: every handle a changed file newly mentions must be the pull
  request's author. Mentions subscribe people to an issue's notifications,
  so only you can add yourself (a team's file gains members as each adds
  their own handle). Removing a handle or a file is fine.

Evaluates the files with nix (on the pull request's runner)."""

import json
import os
import subprocess
import sys
import tempfile

NIXPKGS = "github:NixOS/nixpkgs/nixos-unstable"


def evaluate(source):
    """A notifications file's value, from its Nix source."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sub.nix")
        with open(path, "w") as f:
            f.write(source)
        return json.loads(nix("eval", "--json", "--file", path))


def nix(*args):
    return subprocess.run(
        ["nix", *args], capture_output=True, text=True, check=True
    ).stdout


def mentioned(sub):
    """The handles a file mentions (lowercase): the maintainer, and a team's
    mention list."""
    handles = [sub["maintainer"]] if isinstance(sub.get("maintainer"), str) else []
    handles += [m for m in sub.get("mention") or [] if isinstance(m, str)]
    return {h.lower() for h in handles}


def known_names():
    """({lowercase handles}, {team shortNames}) in nixos-unstable today."""
    found = json.loads(
        nix(
            "eval",
            "--json",
            f"{NIXPKGS}#lib",
            "--apply",
            "lib: { handles = map (m: lib.toLower m.github) "
            "(builtins.filter (m: m ? github) (builtins.attrValues lib.maintainers)); "
            "teams = map (t: t.shortName) "
            "(builtins.filter (t: t ? shortName) (builtins.attrValues lib.teams)); }",
        )
    )
    return set(found["handles"]), set(found["teams"])


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def problems(base, author):
    changed = [
        path
        for path in git(
            "diff",
            "--name-only",
            "--diff-filter=AMR",
            base,
            "HEAD",
            "--",
            "notifications/",
        ).stdout.split()
        if path.endswith(".nix") and os.path.basename(path) != "default.nix"
    ]
    if not changed:
        return [], 0
    handles, teams = known_names()
    found = []
    for path in changed:
        with open(path) as f:
            sub = evaluate(f.read())
        before = git("show", f"{base}:{path}")
        was = mentioned(evaluate(before.stdout)) if before.returncode == 0 else set()
        now = mentioned(sub)
        for handle in sorted(now - handles):
            found.append(
                f"{path}: @{handle} isn't a GitHub handle in nixpkgs' maintainers "
                "(nixos-unstable)"
            )
        team = sub.get("team")
        if isinstance(team, str) and team not in teams:
            found.append(
                f"{path}: {team} isn't a nixpkgs team (its shortName in "
                "nixos-unstable's maintainers/team-list.nix)"
            )
        for handle in sorted(now - was):
            if handle != author.lower():
                found.append(
                    f"{path}: adds @{handle}, but only @{author} can be added by "
                    "this pull request (you can only add yourself)"
                )
    return found, len(changed)


def main(base, author):
    found, changed = problems(base, author)
    for p in found:
        print(f"::error::{p}", file=sys.stderr)
    if found:
        sys.exit(1)
    print(f"notifications/: {changed} changed, names known, nobody added but @{author}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
