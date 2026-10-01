# <picture><source media="(prefers-color-scheme: dark)" srcset="assets/brand/nixkeeper-lockup-dark.svg"><img src="assets/brand/nixkeeper-lockup.svg" alt="nixkeeper" height="80"></picture>

[![CI: tests and lint](https://github.com/iedame/nixkeeper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/iedame/nixkeeper/actions/workflows/ci.yml)
[![Data: daily sync](https://github.com/iedame/nixkeeper/actions/workflows/data-daily.yml/badge.svg)](https://github.com/iedame/nixkeeper/actions/workflows/data-daily.yml)
[![Latest release](https://img.shields.io/github/v/release/iedame/nixkeeper)](https://github.com/iedame/nixkeeper/releases/latest)
[![Dashboard](https://img.shields.io/badge/dashboard-live-8250df)](https://iedame.github.io/nixkeeper/)

Health dashboard for the nixpkgs packages you maintain: new releases, build
and update failures, and vulnerabilities, in one place.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/screenshots/desktop-dark.png">
    <img src="assets/screenshots/desktop-light.png" width="70%" alt="The nixkeeper dashboard on a desktop: a table of packages with their nixpkgs version, open PRs and issues, build and update failures, and one package's update panel open">
  </picture>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/screenshots/mobile-dark.png">
    <img src="assets/screenshots/mobile-light.png" width="22%" alt="The same dashboard on a phone: each package as a card">
  </picture>
</p>

For each package it tracks, nixkeeper shows on one static page (`page/`):

- **New releases**: whether nixpkgs unstable is behind, per
  [Repology](https://repology.org) and nixkeeper's own update checks (a
  project's tags or release page, or for unstable versions its branch;
  about hourly for the ones marked frequent)
- **Build failures**: [Hydra](https://hydra.nixos.org)'s latest builds on
  x86_64-linux, aarch64-linux and aarch64-darwin, and where nixpkgs marks it
  broken
- **Update failures**: the latest attempt of the
  [nixpkgs-update](https://nixpkgs-update-logs.nixos.org) bot (r-ryantm)
- **Vulnerabilities**: versions Repology flags, with their known CVEs
- **Open PRs and issues** in nixpkgs that name the package, with the update
  PR one click away: open (green), or merged and on master (violet)
  while it waits for the channel

A daily sync refreshes it all and keeps a status issue up to date,
commenting when something newly needs attention.

## How it works

```mermaid
flowchart LR
  lists["package-lists/<br>what to track"] --> sync
  subgraph sources [Sources]
    direction TB
    index["nixpkgs channel<br>index, meta.broken"]
    repology[Repology]
    checks["release pages,<br>tags, branches"]
    hydra[Hydra]
    bot["nixpkgs-update<br>logs"]
    gh["GitHub<br>PRs, issues"]
  end
  sources --> sync["daily sync<br>(GitHub Actions)"]
  sources --> hourly["hourly checks"]
  sync --> data[("data branch<br>JSON")]
  hourly --> data
  sync --> issue["status issue"]
  data --> page["the page<br>(GitHub Pages)"]
```

There's no server: nixkeeper is a program that gathers data, and a static
page that shows it. [How it works](docs/how-it-works.md) explains each part;
[Reading the page](docs/reading-the-page.md) explains every dot and badge.

## Get started

**A dashboard of your own on GitHub.** Copy this repository, list your
GitHub handle and any other packages in `package-lists/`, and turn on
GitHub Pages: GitHub Actions syncs it daily, with nothing to host. See
[a dashboard of your own](docs/your-own-instance.md).

**The command, on your computer.**

```bash
nix run github:iedame/nixkeeper -- init --maintainer <your GitHub handle>
```

```bash
nix run github:iedame/nixkeeper -- sync
```

```bash
nix run github:iedame/nixkeeper -- serve
```

That starts your lists, syncs, and shows the page at http://127.0.0.1:8000/.
Installing it, its settings, and pinning a version:
[the nixkeeper command](docs/command.md).

**As a service.** The flake's modules run the sync and the checks on their
own, catch up after the machine was off, and serve the page:

```nix
services.nixkeeper = {
  enable = true;
  lists.maintainers = [ "your-github-handle" ];
};
```

See [nixkeeper on NixOS](docs/nixos.md) or
[nixkeeper on macOS](docs/darwin.md).

## Documentation

- [Reading the page](docs/reading-the-page.md): the dots, badges, panels and tab icon
- [How it works](docs/how-it-works.md): the sync, the sources, what gets tracked
- [A dashboard of your own](docs/your-own-instance.md): your own copy on GitHub
- [The nixkeeper command](docs/command.md): installing, settings, pinning a version
- [nixkeeper on NixOS](docs/nixos.md) and [on macOS](docs/darwin.md): the modules
- [The data](docs/data.md): every field in the JSON, for building on it
- [Troubleshooting](docs/troubleshooting.md): checking that it all runs

## Contributing

How the code is laid out, the commands, and how changes and releases happen
are in [CONTRIBUTING.md](CONTRIBUTING.md); what changed in each version, in
[CHANGELOG.md](CHANGELOG.md). Security problems: [SECURITY.md](SECURITY.md).

## License

nixkeeper's code and its brand assets (`assets/brand/`) are released under
the [MIT License](LICENSE).

The published data (the `data` branch) is collected from other projects and
remains subject to their terms: [Repology](https://repology.org), nixpkgs'
[channel index](https://channels.nixos.org), [Hydra](https://hydra.nixos.org),
the [nixpkgs-update logs](https://nixpkgs-update-logs.nixos.org), GitHub, and
the release pages named in `package-lists/update-checks.nix`.

Fetching the nixpkgs-update logs follows the approach of
[nixpkgs-update-notifier](https://github.com/asymmetric/nixpkgs-update-notifier),
reimplemented here.
