# nixkeeper

[![CI: tests and lint](https://github.com/iedame/nixkeeper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/iedame/nixkeeper/actions/workflows/ci.yml)
[![Data: daily sync](https://github.com/iedame/nixkeeper/actions/workflows/data-daily.yml/badge.svg)](https://github.com/iedame/nixkeeper/actions/workflows/data-daily.yml)
[![Latest release](https://img.shields.io/github/v/release/iedame/nixkeeper)](https://github.com/iedame/nixkeeper/releases/latest)
[![Dashboard](https://img.shields.io/badge/dashboard-live-8250df)](https://iedame.github.io/nixkeeper/)

Health dashboard for the nixpkgs packages you maintain: new releases, build
and update failures, and vulnerabilities, in one place.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/desktop-dark.png">
    <img src="assets/desktop-light.png" width="70%" alt="The nixkeeper dashboard on a desktop: a table of packages with their nixpkgs version, open PRs and issues, build and update failures, and one package's update panel open">
  </picture>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/mobile-dark.png">
    <img src="assets/mobile-light.png" width="22%" alt="The same dashboard on a phone: each package as a card">
  </picture>
</p>

For each package it tracks, nixkeeper shows on one static page (`docs/`):

- **New releases**: whether nixpkgs unstable is behind, per
  [Repology](https://repology.org) and nixkeeper's own update checks (a
  project's tags or release page, or for unstable versions its branch;
  hourly for the ones marked frequent)
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

## Track your own packages

This repository is one instance, tracking iedame's packages and the NixOS
gaming team's. To get a dashboard of your own:

1. **Copy the repository**: "Use this template" on GitHub gives you a clean
   copy (none of this instance's history or data), or fork it (a fork starts
   with its workflows off: turn them on in its Actions tab).
2. **Say what to track** in `package-lists/`:
   - `default.nix`: your GitHub handle under `maintainers`, and your own
     named lists under `extraPackages` (or none);
   - `update-checks.nix` and `ignored-updates.nix`: empty them (`{ }`) or
     replace the entries. They name this instance's packages, and
     `nix flake check` fails on entries for packages you don't track.
3. **Turn on GitHub Pages**: Settings → Pages → Deploy from a branch: `main`,
   folder `/docs`. The page is then at `https://<you>.github.io/<repo>/`.
4. **Run the first sync**: Actions → "Data: daily sync" → Run workflow. It
   takes a few minutes, creates the `data` branch, and opens the status issue
   (labelled `nixkeeper-status`) that the syncs keep up to date. The page
   finds the data by itself; from then on the sync runs daily at 06:00 UTC,
   and the hourly workflow looks for update PRs.
5. **Optionally**, add your own [update checks](package-lists/update-checks.nix)
   and [ignore rules](package-lists/ignored-updates.nix), each documented in
   its file, and update this README's badges and screenshots to point at your
   instance.

The workflows need no secrets: they use the token GitHub gives each run, with
the permissions each workflow declares. GitHub pauses scheduled workflows in
public repositories without activity for 60 days; if the data stops
updating, re-enable the workflow in the Actions tab.

To run it somewhere other than GitHub Actions, see
[Running elsewhere](#running-elsewhere).

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

## Contributing

How the code is laid out, the commands, and how changes and releases happen
are in [CONTRIBUTING.md](CONTRIBUTING.md). Security problems:
[SECURITY.md](SECURITY.md).

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
