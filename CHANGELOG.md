# Changelog

Notable changes to nixkeeper. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0, a minor bump means new
features).

The version lives in `pyproject.toml`; `flake.nix` reads it from there.

## [Unreleased]

### Added

- Platforms where nixpkgs marks a package broken (`meta.broken`, evaluated per
  platform at the channel's commit, since the package index only reflects
  x86_64-linux). They show as "marked broken" (amber) with a link to the
  package source, don't count as failed, and are listed in the status issue
  without notifying.
- Update failures from nixpkgs-update (r-ryantm), read from its public logs:
  the latest attempt per package, recognised as failed, PR opened, PR already
  open, or nothing to update. A failure counts as failed and notifies; one at a
  version nixpkgs has since reached is shown as superseded. Clicking the update
  cell shows the attempt, the end of a failed log, and links to the logs.

- nixkeeper's own update checks (`package-lists/update-checks.nix`): for a
  listed package, the newest version matching a pattern, either among its
  GitHub repository's tags or anywhere on a web page (such as the vendor's
  release notes). If that's newer than nixpkgs', the package counts as
  outdated even while Repology says newest, and the page says the check found
  it. `nix flake check` validates the entries and their patterns. First
  checks: wesnoth-devel (GitHub tags, the 1.19 series) and bbedit (its
  updates page).

- Sources that couldn't be refreshed are shown, not just logged: when an
  update check (GitHub or web page), Hydra or the nixpkgs-update logs fail, the
  row keeps its last known result and says so, with the reason and since when
  ("check failing" badge, "not refreshed" tags, a note in the panels). The
  status issue lists them under "Not refreshed" and comments once per newly
  failing source; working again is listed quietly.

- Packages Repology flags as vulnerable link to its list of known CVEs, in
  the package details and in the status issue.

- Hourly quick check (`nix run .#quick-check`, `quick-check.yml`): update
  checks marked `frequent = true` also run every hour against the last
  published data, refreshing just those packages' Repology data. Writes,
  commits and notifies only when something changed. First ones: google-chrome
  (Google's version history API) and microsoft-edge (Microsoft's Debian
  repository), Linux stable.

- MIT license (`LICENSE`, also declared in `pyproject.toml` and the flake's
  package metadata). The README notes where the published data comes from.

- Runs outside GitHub too (groundwork for self-hosting): the data directory,
  the package lists (Nix folder or JSON), a token file, the notification
  method and the page URL are settings (see the README). The page finds its
  data next to itself, through a `<meta>` setting, or on GitHub as before.

- Filters for the package lists: `extraPackages` in `package-lists/default.nix`
  holds named lists (`extra`, `gaming-team`), and the page shows a filter for
  each next to `maintained` (packages found through `maintainers`). The counts
  follow it, and `?list=<name>` is a shareable page of one list. A plain list
  still works, as `extra`.

### Changed

- Described as what it has become: "Health dashboard for the nixpkgs packages
  you maintain", in the README (with what it checks), the page ("your nixpkgs
  packages, at a glance"), `flake.nix` and `pyproject.toml`.
- Notifications go through a choice of method (`NIXKEEPER_NOTIFY`); the status
  issue is `github-issue` (the old value `1` still works). It never posts with
  the local `gh` login.
- The daily sync and the quick check share a concurrency group, so they never
  push to the data branch at the same time.
- Hydra and the update logs share one retrying HTTP helper.
- "Outdated" means outdated per Repology or per an update check, everywhere:
  the page, "outdated since" and the status issue.

### Fixed

- The data directory was fixed when the code loaded, so functions defaulting
  to it ignored a later setting.

## [0.2.0] - 2026-09-28

### Added

- Build failures from Hydra (jobset `nixpkgs/unstable`, i.e. master) for each
  tracked package on x86_64-linux, aarch64-linux and aarch64-darwin, limited to
  the platforms it declares. Unfree packages, which Hydra doesn't build, are
  skipped.
- Build panel on the page: clicking a row's build cell shows each platform's
  result, with links to the build or its log and when a failing job last built
  successfully. It shares the space under the row with the package details.
- Status issue: one issue in this repository, rewritten on every sync, listing
  what's failed, outdated, flagged vulnerable or not refreshed. A comment (which
  is what notifies) is posted when something newly needs attention, including a
  package starting to fail on another platform; good news is only listed.
- Links to where nixpkgs defines each package, at the channel's exact commit
  and line.
- Workflow warnings when GitHub search counts look wrong (failed searches, or
  every PR count equal to its issue count).
- `nix flake check` validates the package lists (unknown attributes or
  maintainer handles, aliases such as `python3Packages`, duplicates) and runs
  formatting and lint checks (nixfmt, ruff, biome, deadnix, statix,
  actionlint). `nix fmt` formats everything.
- This changelog.

### Changed

- The page is split into `index.html`, `app.js` and `style.css`.
- The "failed" filter follows the platform filter: with macOS selected, a
  failure only on Linux doesn't count.
- A Repology domain that answers is tried first for the rest of the run, so an
  unreachable repology.org costs one failed connection instead of one per
  lookup.
- Workflows use `actions/checkout@v7`.
- The flake takes its version from `pyproject.toml`.

### Fixed

- PR counts in CI came back equal to issue counts: the sync workflow now has
  `pull-requests: read`.
- actionlint found no workflows in the Nix check (no `.git` there); they're
  passed explicitly.

## [0.1.0] - 2026-09-28

First versioned release, covering everything from the start of the project up
to its restructuring into a Python package.

### Added

- Daily sync (GitHub Actions) that compares tracked nixpkgs-unstable packages
  with Repology and publishes the results to the `data` branch.
- Static page (GitHub Pages) reading that data:
  - clickable counts for tracked, outdated, failed and flagged-vulnerable
    packages, following Repology's wording;
  - separate rows for stable and devel variants (wesnoth / wesnoth-devel),
    with a shaded "devel" badge;
  - how long each package has been outdated;
  - platform tags (Linux, macOS) that filter the list;
  - open nixpkgs PR and issue counts, from title-only GitHub searches by
    attribute name;
  - sorting by what needs attention (failed, then longest outdated) or A–Z;
  - filters, search and sort kept in the address;
  - a warning when the data is more than two days old;
  - placeholder columns for build and update failures.
- Package lists in `package-lists/`: every package maintained by the listed
  GitHub handles, plus extra packages by attribute (nested sets such as
  `haskellPackages.foo` included) or pname.
- Package metadata (maintainers, platforms, homepage) from the nixos-unstable
  channel's package index, without evaluating nixpkgs.
- Repology lookups by nixpkgs attribute, falling back to the project name.
- Retries, a fallback Repology domain, and reuse of the previous run's data
  (marked "not refreshed") when a lookup fails; the run aborts if most fail.
- GitHub searches batched through GraphQL.
- Unit tests, run on every build and in CI.
- `nix run .#sync` (alias `.#fetch`).

### Changed

- The data directory is rebuilt on every run and swapped in at the end, so
  packages removed from the lists don't leave files behind.
- The sync script is a Python package (`nixkeeper/`) with tests in `tests/`.

[unreleased]: https://github.com/iedame/nixkeeper/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/iedame/nixkeeper/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/iedame/nixkeeper/releases/tag/v0.1.0
