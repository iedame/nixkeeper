# Changelog

Notable changes to nixkeeper. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0, a minor bump means new
features).

The version lives in `pyproject.toml`; `flake.nix` reads it from there.

## [Unreleased]

### Added

- The page links to nixkeeper's repository ("source and how it works") and
  to what its statuses and badges mean in its footer, and a copy of nixkeeper
  on GitHub Pages also links to its own package lists.
- The README explains how to set up a dashboard of your own ("Track your own
  packages"), with screenshots of the page. How the code is laid out, the
  commands, and how changes and releases happen moved to
  `CONTRIBUTING.md`.
- The README explains how nixkeeper works (with a diagram) and how to read
  the page: every dot, badge and column state. `DATA.md` describes the data
  files, field by field, and `CONTRIBUTING.md` maps the code.
- Issue forms: "Track a package" and "Something looks wrong".
- The page has a description, for search engines and link previews.
- Ignore rules for update attempts (`package-lists/ignored-updates.nix`): a
  version nixpkgs-update tried and failed that shouldn't count, such as one
  upstream never really released. Its failure shows as superseded, with the
  rule's reason; a failure at any other version still counts. The sync notes
  when a rule no longer matches the bot's latest attempt. First one: xskat's
  4.0-9.

- Update checks for unstable versions (`github` + `branch` in
  `package-lists/update-checks.nix`): for a package whose nixpkgs version is
  `…-unstable-YYYY-MM-DD`, the commits since then on the branch it follows.
  Repology can't tell: it only tracks releases, and marks unstable versions
  "untrusted". The package counts as outdated once one of those commits has
  waited 90 days; `outdatedAfter = { days = …; commits = …; }` changes that
  per package (whichever comes first; `null` turns one off). Until then, the
  details list the newer commits as not counted yet. First one: stepmania
  (its `5_1-new` branch).

- The build panel says which version last built on a failing platform, with
  a link to that build, next to the version that fails ("failed at 1.2.4 ·
  last succeeded at 1.2.3"). When both are the same, the version didn't break
  it; something else did (a dependency, the toolchain). Platforms that didn't
  build because of a dependency, or didn't finish, now show when they last
  succeeded too.
- Dependabot (`.github/dependabot.yml`) proposes updates to the actions the
  workflows use, weekly.
- A security policy (`SECURITY.md`): report vulnerabilities privately
  through GitHub's private vulnerability reporting.

### Changed

- The page fits narrow screens without scrolling sideways. On phones and
  windows up to 940px wide, each package is a card: its name and platforms,
  then its version and badges, then only what needs attention (build or
  update failures, open PRs and issues). The panels wrap to fit. In the
  table, a long version wraps (before "→", never inside a version) and
  platform tags go under the name when space is short, instead of widening
  the table past the screen.
- An outdated unstable version shows only the new date as its target
  ("5.1.0-b2-unstable-2022-11-14 → 2026-08-22"); the full version is in its
  tooltip and the details.

### Fixed

- A nixpkgs-update attempt that found a newer version but had no way to
  update the package ("The diff was empty after rewrites", e.g. a package
  with several hashes and no updateScript) showed as "nothing to update". It
  now shows as an amber "can't update", with the bot's reasons from the log:
  not a failure, but a sign the update needs doing by hand. After an
  updateScript run (`0 -> 1`), an empty diff still means nothing to update.
- Opening a package's details no longer shifts the table's columns: the
  panel's long list of repositories made the table redistribute its width, so
  the rows above moved (by up to ~90px). On a phone, a repository chip with a
  long version that can't break (`5.1.0~20221114gitd55acb1`) no longer sticks
  out past the screen; its version wraps inside the chip.

### Security

- The workflows' actions are pinned to commits (`nix-installer-action` ran
  from its `main` branch), so a change upstream can't run with the workflows'
  write access unreviewed. CI only gets read access, and CI and the release
  workflow don't keep the token in the checkout.
- Links on the page from data (homepages, update-check pages, logs, PRs,
  sources) are shown only if they're web addresses (`https:` or `http:`): a
  `javascript:` link, which escaping doesn't stop, isn't linked.

## [0.4.0] - 2026-09-29

### Added

- "On master": when master has a newer version than the nixos-unstable
  channel (built by Hydra, or brought by an update PR merged into master, so
  before Hydra has built it), the row says so, and an outdated package whose
  update is merged shows as waiting for the channel: in GitHub's merged-PR
  purple (its status dot and age, an "on master" badge like GitHub's "Merged"
  label, linking to the merged PR, and a note in the details), sorted after
  the other outdated packages. It doesn't trigger "Newly outdated" in the
  status issue. PRs merged into staging don't count: they reach master weeks
  later.
- Update PRs: an open PR updating a package (title
  `<attribute>: <old> -> <new>`, aiming past nixpkgs' version) shows as a
  badge linking to it, in GitHub's open-PR green (grey while a draft). The
  status issue links it too.
- Hourly PR check (`nix run .#pr-check`): the update PRs of every outdated
  package, open and merged into master, so those badges show within the hour.
  One GitHub request; it commits only when a badge changes.
- Release workflow ("Release: publish from tag", `release.yml`): pushing a
  version tag publishes a GitHub Release with that version's changelog
  section as notes, after checking the tag against `pyproject.toml` and the
  changelog and running the flake checks.

### Changed

- Workflows are named for what they do: "CI: tests and lint" (`ci.yml`, was
  `check.yml`), "Data: daily sync" (`data-daily.yml`, was `sync.yml`) and
  "Data: hourly updates (frequent packages, update PRs)" (`data-hourly.yml`,
  was `quick-check.yml`).
- The hourly workflow runs the frequent update checks (`nix run
  .#frequent-check`, renamed from `quick-check`, which still works) and the PR
  check, with one commit. The frequent check no longer refreshes GitHub
  counts: those stay daily.

### Fixed

- An update failure clears as soon as nixpkgs has moved on from the version
  the bot tried to update (someone updated it another way), shown as
  "superseded". Before, it only cleared at the bot's next attempt, up to ~10
  days later, for packages with their own update script (`0 -> 1` in the
  log), such as wesnoth-devel.
- A failure also counts as superseded once master has moved on (the fix is
  merged, not yet in the channel), so a row waiting for the channel doesn't
  also show as failed.
- The update cell shows a superseded failure as a grey "superseded" instead of
  "none reported", so a bot attempt that broke stays visible.

## [0.3.0] - 2026-09-28

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

[unreleased]: https://github.com/iedame/nixkeeper/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/iedame/nixkeeper/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/iedame/nixkeeper/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/iedame/nixkeeper/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/iedame/nixkeeper/releases/tag/v0.1.0
