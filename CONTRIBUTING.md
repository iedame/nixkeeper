# Contributing to nixkeeper

How the code is laid out, how to work on it, and how changes and releases
happen. For what nixkeeper does and how to set up your own, see the
[README](README.md).

## Layout

- `nixkeeper/`: the sync, as a Python package
  - `sources/`: where the data comes from: the nixpkgs index and package
    lists, Repology, GitHub, Hydra, the nixpkgs-update logs, and the update
    checks
  - `tracking.py` → `lookup.py` → `rows.py` → `history.py` → `output.py`,
    run in that order by `__main__.py`; `frequent.py` and `prcheck.py` are
    the hourly checks
- `tests/`: offline tests, one file per module
- `nix/package-lists.nix`: `nix flake check` validates the package lists
  against nixpkgs (typos, aliases like `python3Packages`, unknown maintainer
  handles, duplicates, malformed update checks and ignore rules)
- `package-lists/`: what this instance tracks (see the README)
- `docs/`: the page (`index.html`, `app.js`, `style.css`), reading `data/`
  from the `data` branch
- `assets/`: screenshots of the page, for the README (light and dark,
  desktop and phone) and the repository's social preview
- `.github/workflows/`:
  - `ci.yml`, **CI: tests and lint**: checks nixkeeper's own code on every
    push and PR
  - `data-daily.yml`, **Data: daily sync**: updates all package data
  - `data-hourly.yml`, **Data: hourly updates (frequent packages, update PRs)**:
    the frequent update checks and outdated packages' update PRs
  - `release.yml`, **Release: publish from tag**: a GitHub Release for each
    version tag (see [Releasing](#releasing))

## Commands

```bash
nix run .#sync            # sync into data/ (alias: nix run .#fetch)
nix run .#frequent-check  # only the frequent update checks, against data/ (hourly in CI)
nix run .#pr-check        # outdated packages' update PRs, against data/ (hourly in CI)
nix fmt                   # format everything (Nix, Python, the page)
nix flake check           # tests, formatting, linters, package-list checks
nix develop -c python3 -m unittest discover -s tests -t .   # tests, quickly
nix eval --json -f package-lists                             # what the lists evaluate to
```

New files must be `git add`ed before Nix sees them.

## Changes

`main` only changes through pull requests: squash-merged, once CI
(`tests-and-lint`) passes, so each PR is one commit on `main`, titled after
the PR. Direct and force pushes to `main` are blocked (repository rulesets).
Changes that users would notice go in `CHANGELOG.md` under `## [Unreleased]`,
in the same PR.

Security problems go through the [security policy](SECURITY.md), not a
public issue.

## Releasing

1. In a PR titled `chore: release x.y.z`: set the new `version` in
   `pyproject.toml` (the flake reads it from there), and turn
   `## [Unreleased]` in `CHANGELOG.md` into `## [x.y.z] - date` (with a fresh
   `## [Unreleased]` above it, and its compare link below).
2. Once merged, tag the merge commit on `main` and push the tag:
   `git switch main && git pull`, `git tag vx.y.z`, `git push origin vx.y.z`.

The release workflow checks that the tag matches `pyproject.toml` and has a
changelog section, runs the flake checks, and publishes the GitHub Release
with that section as its notes. If a check fails, nothing is published.

Version tags can't be moved or deleted (a tag ruleset), so a published
version never changes. If a release fails, fix it in a PR and release the next
patch version (x.y.z+1) instead of reusing the tag; a tag whose release
failed stays unreleased.
