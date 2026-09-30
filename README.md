# nixkeeper

Health dashboard for the nixpkgs packages you maintain: new releases, build
and update failures, and vulnerabilities, in one place.

For each package it tracks, nixkeeper shows on one static page (`docs/`):

- **New releases**: whether nixpkgs unstable is behind, per
  [Repology](https://repology.org) and nixkeeper's own update checks (a
  project's tags or release page, hourly for the ones marked frequent)
- **Build failures**: [Hydra](https://hydra.nixos.org)'s latest builds on
  x86_64-linux, aarch64-linux and aarch64-darwin, and where nixpkgs marks it
  broken
- **Update failures**: the latest attempt of the
  [nixpkgs-update](https://nixpkgs-update-logs.nixos.org) bot (r-ryantm)
- **Vulnerabilities**: versions Repology flags, with their known CVEs
- **Open PRs and issues** in nixpkgs that name the package, with the update
  PR one click away: open (GitHub's green), or merged and on master (purple)
  while it waits for the channel

A daily sync (GitHub Actions, or anywhere: see [Running elsewhere](#running-elsewhere))
refreshes it all and keeps a status issue up to date, commenting when something
newly needs attention.

## What gets tracked

`package-lists/default.nix` lists GitHub handles under `maintainers` (every
nixpkgs package they maintain is tracked) and imports further named lists
under `extraPackages` (`extra`, `gaming-team`, ...) of nixpkgs attribute names
(exactly that package, e.g. `haskellPackages.pandoc`) or pnames (every
top-level package with that pname).

Each list is a filter on the page, next to `maintained` for the packages
found through `maintainers`. `?list=gaming-team` in the address is a page of
just that list, to share with the people it's for.

## Layout

- `nixkeeper/`: the sync, as a Python package
  - `sources/`: nixpkgs index + package lists, Repology, GitHub
  - `tracking.py` → `lookup.py` → `rows.py` → `history.py` → `output.py`,
    run in that order by `__main__.py`
- `tests/`: offline tests, one file per module
- `nix/package-lists.nix`: `nix flake check` validates the package lists
  against nixpkgs (typos, aliases like `python3Packages`, unknown maintainer
  handles, duplicates)
- `docs/`: the page (`index.html`, `app.js`, `style.css`), reading `data/` from the `data` branch
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

## Running elsewhere

Everything defaults to running from a checkout with the GitHub workflows.
Elsewhere (a server, a service), these environment variables change that:

| Variable | Default | What it sets |
|---|---|---|
| `NIXKEEPER_DATA_DIR` | `data` | where the data is written, and the previous run read from |
| `NIXKEEPER_LISTS` | `package-lists` | the package lists: that Nix folder, or a JSON file of what it evaluates to |
| `NIXKEEPER_GITHUB_TOKEN_FILE` | – | a file holding a GitHub token (else `GITHUB_TOKEN`, else the local `gh` login) |
| `NIXKEEPER_NOTIFY` | `none` | `github-issue` to keep the status issue up to date (the workflows set it) |
| `NIXKEEPER_GITHUB_REPO` | the workflow's repo | where the status issue lives |
| `NIXKEEPER_PAGE_URL` | the GitHub Pages site | the page link in notifications |

The status issue is only posted with a token given explicitly (the token file
or `GITHUB_TOKEN`), never with the local `gh` login.

The page finds its data by itself when `data/` is served next to it. Otherwise
it reads the repository's `data` branch on a GitHub Pages site, or wherever
`<meta name="nixkeeper-data" content="…">` in `docs/index.html` points.
`?data=<url>` (same site only) overrides it for testing.

## License

nixkeeper's code is released under the [MIT License](LICENSE).

The published data (the `data` branch) is collected from other projects and
remains subject to their terms: [Repology](https://repology.org), nixpkgs'
[channel index](https://channels.nixos.org), [Hydra](https://hydra.nixos.org),
the [nixpkgs-update logs](https://nixpkgs-update-logs.nixos.org), GitHub, and
the release pages named in `package-lists/update-checks.nix`.

Fetching the nixpkgs-update logs follows the approach of
[nixpkgs-update-notifier](https://github.com/asymmetric/nixpkgs-update-notifier),
reimplemented here.
