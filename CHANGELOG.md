# Changelog

Notable changes to nixkeeper. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0, a minor bump means new
features).

The version lives in `pyproject.toml`; `flake.nix` reads it from there.

## [Unreleased]

### Changed

- The page stays responsive with big lists. With 3,000 packages, redrawing
  the list on a phone or tablet takes about a third of the time it did (cards
  off screen are only laid out when scrolled near), searching redraws once
  typing pauses instead of at every key, and a row's panel is only made when
  it's first opened. On wide screens, a table of that size still takes about
  half a second to redraw on a fast computer: about a quarter of a second at
  1,500 packages.

- The `data` branch no longer piles up a commit for every sync and hourly
  update: each run publishes `main` plus one commit with the latest data,
  replacing the last (the history was never read). The first run after
  updating does this to the existing branch, keeping its data. If GitHub
  can't say whether the branch exists, the run now stops at once, instead of
  carrying on as if it were the first run (against no previous data).

- Each package's Repology file in `data/` keeps only what nixkeeper reads
  (`repo`, `srcname`, `version`, `status`, `vulnerable`), each entry once,
  instead of everything Repology returns: about 4 times smaller (1.4 MB to
  0.35 MB for 70 packages, about 30 MB to 7 MB at 1,500), and about 3 times
  less to download for the details panels. If you read these files yourself,
  the other fields are gone.

- Fewer requests to the sources, for the same results:
  - Repology: each package is looked up by the project the last sync found
    for it, one request instead of two (asking by attribute is answered
    with a redirect to the project). If Repology has moved the package to
    another project, it's looked up by attribute as before.
  - nixpkgs-update's logs: the log site's index (one request, compressed)
    says when each package's logs last changed, so a package whose logs
    haven't changed since the last sync isn't listed again, and one with no
    logs isn't asked about. For 72 attributes, a sync now made 3 requests
    instead of at least 72, with the same results.

  At 1,500 packages that's about 2,800 fewer requests a day. The time
  estimate at the start of a sync doesn't count it yet: it'll be measured
  from real runs first.

### Fixed

- `repoCount` counted Repology's entries, so a repository listing a package
  more than once (subpackages) counted more than once. It now counts
  repositories, as documented.
- When a package's Repology file couldn't be loaded (a network hiccup, say),
  its details said "compared with 0 other repositories". They now say the
  file couldn't be loaded, and opening the package again tries again.

## [0.10.0] - 2026-10-04

### Added

- `follows`, a new kind of update check, for a package updated together with
  another, to the same version, by the same PRs:
  `msedgedriver = { follows = "microsoft-edge"; };`. It counts the other's
  newest version and update PRs (merged and open) as its own, in the daily
  sync and the hourly checks; their titles name only the other package, so
  nixkeeper couldn't find them before. Checked like the other kinds (the
  package followed has to be tracked too; no chains). The community update
  checks have it for msedgedriver.

- Up-to-date rules (`package-lists/up-to-date.nix`, `upToDate` in the
  lists), for a version nixpkgs has that Repology gets wrong: calls it
  untrusted, incorrect or ignored, or compares it with a version that isn't
  really newer. A rule names the version, the version Repology shows as
  newest elsewhere, and why nixpkgs' is right; while nixpkgs has that version
  and Repology shows nothing newer, the row counts as up to date, and its
  details say why and what Repology said. A real new release or nixpkgs
  moving on ends it, and the sync says the rule can go. Only Repology's
  verdict changes: update checks and master still count. The community rules
  have them too (`community.upToDate = true;`, `lists.community.upToDate` in
  the modules), for asc, pacvim, steamtinkerlaunch and wesnoth-devel, and
  `nixkeeper community-check` and the weekly run report the ones that can go.

- Fewer requests to the nixpkgs-update logs: a sync no longer downloads the
  log of an attempt it read the day before (the bot tries each package about
  every ten days), and takes the previous reading instead, judged afresh
  against nixpkgs and the ignore rules. Each attempt records the version of
  the rules it was read with (`parser`), so a fix to how logs are read
  applies at the next sync.

- Keeping syncs reasonable as the lists grow: a sync starts by saying how
  long it should take (and on GitHub, in the run's summary); from 500
  packages the list check warns, on the page and in the status issue; above
  2,000 the sync refuses to start, unless the lists raise the limit with
  `maxPackages` (`lists.maxPackages` in the modules). Each package costs
  about 8 requests to public services and 7 seconds per sync.

### Changed

- When a source answers "too many requests" or "unavailable" with how long
  to wait (`Retry-After`), nixkeeper waits that long before trying again,
  up to 5 minutes; asked to wait longer, it gives that request up and the
  package keeps its previous data. GitHub's rate limits get the same: one
  more try after the wait it asks for.

- nixkeeper introduces itself properly to the sources it reads: its
  User-Agent is now `nixkeeper/<version> (+https://github.com/iedame/nixkeeper)`
  (it was a fixed `nixkeeper/1.0 (personal package tracker)`), plus the
  repository running it on GitHub Actions. Self-hosters can add how they can
  be reached with `NIXKEEPER_CONTACT` (`contact` in the modules).

- When master is partway there (an update merged, waiting for the channel,
  and a newer release already out, as with Chrome's quick security
  releases), the page shows master's version on a line of its own with its
  `on master` badge, between nixpkgs' version and the newest with its PR.
  Clicking the versions then copies the next update's title, from master's
  version.

### Fixed

- `nixkeeper community-check NAME` tried each name as both an update check
  and an ignore rule: a package with only an update check said its "ignore
  rules still apply", and one with only ignore rules failed as a missing
  update check. Each name is now tried for the rules it has; a name with
  neither is reported as such (a typo, most likely).
- A package only Nix packages (msedgedriver) showed its update as `→ ?`:
  Repology marks no repository "newest" then, but the one ahead (a stable
  branch with a backport) "unique", which now counts. The newest version is
  also the highest of those Repology marks, not the first listed. Should no
  newer version be known, the page says "newer version unknown".
- `ignoredUpdates` couldn't match a failed `updateScript` run, because the
  bot's log header writes `0 -> 1` instead of the versions. When the script
  wrote a diff before the build failed, nixkeeper now reads the versions from
  that diff (so the page also shows `from → to` instead of `updateScript`).
  When the script failed before picking a version (such as `nix-update`
  mistaking an older tag for newer), a rule for the version nixpkgs has
  ignores the failure while the package is up to date, and lets it show again
  once a newer release is out. The community ignore rules have it for
  blackvoxel 2.5.

### Security

- The page builds its markup with an `html` template tag that escapes every
  value from the data (package names, PR titles, rule reasons, ...) unless
  it's markup the page writes itself, instead of an `escapeHtml` call at
  each of about 50 places: a value can't add markup by a forgotten escape.
  Nothing on the page looks different. And `?owner=&repo=`, which points the
  page at another repository's data, now only takes names GitHub allows.

## [0.9.0] - 2026-10-01

### Added

- A link to nixkeeper's repository on the page: a GitHub button in the
  toolbar, and a quiet last line with the version that made the data
  ("nixkeeper 0.9.0 on GitHub"). The sync writes that version into
  `index.json` (`version`).
- Link previews for the page: shared on Discourse, Matrix, Mastodon and
  the like, a link to a nixkeeper page shows nixkeeper's card (the social
  preview). Releases' notes start with the card too.
- Screenshots in both palettes (`assets/screenshots/*-catppuccin.png`); the
  README shows the Catppuccin ones in a collapsible section.
- A Theme menu on the page: Classic or [Catppuccin](https://catppuccin.com)
  colours (Latte when light, Mocha when dark), and light, dark or Auto (the
  system's setting). The choice is kept in the visitor's browser and applied
  before the page draws. The page's owner sets the default palette with
  `page.theme = "catppuccin";` in the package lists (`lists.page.theme` in
  the modules); the sync checks it and writes it to the data.
- Community rules (`community/`): rules anyone can add by pull request, for
  any nixpkgs package, in the format of your own lists: update checks
  (`community/update-checks.nix`, where to look for new releases) and ignore
  rules (`community/ignored-updates.nix`, failed nixpkgs-update attempts that
  don't count). Opt in to each in your package lists,
  `community = { updateChecks = true; ignoredUpdates = true; };` (or
  `lists.community` in the modules): each sync then uses them for the
  packages you track, and only those, your own rules winning (an update
  check per package, an ignore rule per version). They come with nixkeeper,
  so they change only when you update it, and the page says when a result
  comes from one. Because community update checks run on every subscriber's
  machine, they're held to limits: web pages over https to public hosts only
  (redirects too), at most 2 MB; short patterns without the shapes that can
  take forever. One beyond them is refused, never fetched. See
  `docs/community.md`.
- Keeping the community rules healthy: CI checks `community/` on every pull
  request (each rule well formed, for a package in nixpkgs; update checks
  within the limits, their patterns valid). The "Community: update checks
  still work" workflow tries every rule for real weekly and keeps a
  "Community rules status" issue up to date: which update checks are broken,
  why and since when (commenting when one breaks or works again), and which
  ignore rules can go, the bot having moved on. On pull requests it tries the
  rules they add or change, failing if an update check finds nothing or an
  ignore rule doesn't match the bot's latest failed attempt.
  `nixkeeper community-check [NAME...]` (`nix run .#community-check` from a
  checkout) does the same by hand, to try a rule before proposing it; there's
  also an issue form for proposing an update check.
- `docs/troubleshooting.md`: how to check that nixkeeper runs as it should on
  GitHub, as the command, and with the NixOS and nix-darwin modules (the
  jobs, their schedules, logs and data), and what the page's warnings mean.

### Changed

- The page, refreshed:
  - The toolbar: a search field with an icon and a `/` shortcut, and icon
    buttons for A–Z and the Theme menu. The Refresh button is gone
    (reloading does the same).
  - The counts and the lists are one bar of filter chips. On phones and
    tablets it's one row that swipes sideways and stays at the top while
    scrolling. On desktop, the header, the filters and the table's column
    headings stay at the top.
  - Versions: the newest version sits under nixpkgs', with the part that
    changes in colour. Click them to copy the update's title as nixpkgs
    writes it (`unciv: 4.22.1 -> 4.22.6`). The update's badge (PR, on
    master) and the rest line up at the right of the versions. How long a
    package has been outdated shows after its name.
  - Quieter rows: "none reported", "not built by Hydra", "not attempted"
    and "superseded" are muted, and zero PR or issue counts are faint, so
    what needs a look stands out.
  - The platforms are one small label under the package's name. Rows open
    with a clearer chevron, and the open row and its panel read as one.
  - A package's panel compares nixpkgs with one entry per repository,
    newest first: the first 8, then "Show all".
  - The legend is a `?` beside "checked …" that opens what each dot means
    (on master's violet included), and each row's dot says so on hover.
    Hovering "checked …" shows the exact time of the last sync.
  - A package's panel: rounded repository chips under a small heading, and
    "compared with N other repositories" counting them the way it shows
    them.
  - Touch screens get larger targets, and animations stop when the system
    asks for reduced motion.
  - The card layout now starts below 1080px (was 940px).
- The documentation lives in `docs/`, one page per topic: reading the page,
  how it works, a dashboard of your own, the command, the NixOS and
  nix-darwin modules, the data (was `DATA.md`) and troubleshooting. The
  README is now a short introduction with the three ways to start, and
  links to them; the page's "what these mean" link goes to
  `docs/reading-the-page.md`.
- The nix-darwin module's logs (`~/Library/Logs/nixkeeper/`) date each run:
  a line with the time and the job's name before its output, and one with
  how it ended after it, so a run can be told from the next (and the
  catch-up from the daily sync, which share `sync.log`).

## [0.8.0] - 2026-10-01

nixkeeper as a service: modules for NixOS and nix-darwin that run the sync
and the frequent checks on their own, catch up after the machine was off,
and serve the page. Also: master's newer version counts as "on master" by
itself, and every sync checks the package lists for mistakes.

### Added

- A NixOS module (`nixosModules.default`, `services.nixkeeper`): the sync
  daily and the frequent and update PR checks hourly on systemd timers, as
  their own hardened user, with the lists in the configuration, a GitHub
  token as a systemd credential, and optionally the page and its data on
  nginx. At boot, and when first enabled, it syncs if there's no data yet or
  the last sync is over 20 hours old. Tested in a NixOS VM in CI.
- A nix-darwin module (`darwinModules.default`, `services.nixkeeper`): the
  same jobs as launchd agents of your user, on the command's own folders
  (or the lists in the configuration), with their output in
  `~/Library/Logs/nixkeeper/`, and optionally `nixkeeper serve` kept running
  for the page on this Mac. At login, and when first loaded, it syncs if
  there's no data yet or the last sync is over 20 hours old. Lists or a data
  folder set in the configuration are also exported to your shell, so
  commands you type agree with the jobs.
- Runs on the same data take turns: `sync`, `frequent-check`, `pr-check`
  and `page` hold a lock next to the data folder (`<data dir>.lock`), and a
  second run waits for the first, saying so.
- `nixkeeper sync --if-older HOURS`: only sync when there's no data yet or
  the last sync is older than that.
- Every sync checks the package lists for mistakes that would otherwise go
  unnoticed: a maintainer handle no nixpkgs package lists (a typo would track
  nothing), an extra package nixpkgs doesn't have, and an update check or
  ignore rule for a package that isn't tracked. They're in the sync's log and
  the data (`listProblems`), and the page shows them above the table, so
  lists set in a NixOS or nix-darwin configuration, or by `nixkeeper init`,
  get the same safety net as the repository's `nix flake check`.
- The README says how to pin nixkeeper to a release, a version tag in the
  flake input's URL, instead of following `main`.

### Changed

- `nixkeeper serve` starts before the first sync: the page says it has no
  data yet, and shows it once a sync has written it.
- A package whose master already has a newer version than the channel
  (Hydra's build) counts as outdated, with that version as the one to update
  to, and shows "on master": waiting for the channel, nothing to do. Before,
  it only did when Repology or an update check knew of the new release too
  (wesnoth-devel's 1.19.28 showed as up to date without its update check).

## [0.7.0] - 2026-10-01

nixkeeper as a program you can install and run yourself: one `nixkeeper`
command that works from anywhere, `nixkeeper init` to start your lists, and
the page shipped with it (`nixkeeper serve`, `nixkeeper page`). Forks: set
Settings → Pages → Source to "GitHub Actions" after updating (see Changed).

### Added

- One `nixkeeper` command, with a subcommand for each job: `nixkeeper sync`,
  `nixkeeper frequent-check` and `nixkeeper pr-check`, plus `nixkeeper paths`
  (where the lists and data are, and which setting says so) and
  `nixkeeper --version`. Flags (`--lists`, `--data-dir`, `--notify`) set what
  the `NIXKEEPER_*` variables do, and win over them. `nix run .#sync` and the
  other apps run the new command; the old names (`nixkeeper-sync`,
  `nixkeeper-frequent-check`, `nixkeeper-pr-check`) still work until 1.0,
  with a hint.
- `nixkeeper init --maintainer <handle>` starts your package lists: a folder
  of Nix files with your handle and commented examples, to edit.
- The page ships with nixkeeper (also as `share/nixkeeper/www/` in the
  package). `nixkeeper serve` shows it on this computer with the data as it
  is; `nixkeeper page <dir>` writes it with a copy of the data into a folder
  for any static host.
- `nix/package.nix`: nixkeeper's package in nixpkgs' style (the same file,
  with a release as its source, can later go to nixpkgs), with a version
  check and the package's metadata. It installs with
  `nix profile install github:iedame/nixkeeper`.
- Tests for the page: its rules (statuses, version order, "on master",
  ages, safe links, the tab icon's signals) moved into `page/logic.js`, which
  `tests/js/` tests with Node's test runner as part of `nix flake check`. The
  lint check now also catches undeclared variables in the page's code.

### Changed

- The `nixkeeper` command works from anywhere: by default it keeps the lists
  in `~/.config/nixkeeper/package-lists/` (or `lists.json` there) and the
  data in `~/.local/state/nixkeeper/data/`, following the XDG variables.
  `nix run .#sync` and the other apps still use the checkout's
  `package-lists/` and `data/`, so the workflows and local runs from a
  checkout are unchanged; `nix run .` (and `nix run github:iedame/nixkeeper`)
  is now the command itself, on your own folders, rather than a sync.
- A workflow publishes the page to GitHub Pages ("Pages: publish the page")
  whenever it changes on `main`, instead of Pages deploying a folder from
  the branch. Forks set Settings → Pages → Source to "GitHub Actions", then
  run the workflow once (see the README's setup steps).
- The page's folder is `page/` instead of `docs/`: it's the page, not
  documentation, and the workflow that publishes it can take any folder.
- Missing package lists, lists that don't evaluate, and a missing `nix` stop
  the sync with a message saying what to do, not a traceback.

## [0.6.0] - 2026-10-01

nixkeeper's own visual identity: a mark, a wordmark and colours, on the page,
in the README and in the repository's social preview.

### Added

- nixkeeper's mark: a hexagonal ring of three chevrons (new releases, build
  and update failures, vulnerabilities) around a solid centre (the package),
  in violet turning to mauve. It's the page's favicon.
- The wordmark: "nixkeeper" in Oxanium Bold, lowercase. The lockups (the mark
  with the wordmark) carry it as outlines, so they look the same everywhere
  without the font, on transparent backgrounds for light and dark. The
  page's header and the README's title are now the lockup.
- The page's tab icon shows what needs attention: the mark's chevrons light
  up for a new release (orange), a failure or a vulnerability (pink), and the
  releases chevron turns green when all is well. It follows the list filter,
  like the counts.
- nixkeeper's identity, in `assets/brand/`: a guide (`BRAND.md`), the mark
  and its variants, status versions (all good, a new release, a failure, a
  vulnerability), lockups, colour tokens and an identity sheet, generated by
  `scripts/brand/` (`nix run .#brand`, which fetches the wordmark's font, one
  pinned file, and outlines it with HarfBuzz). Under the MIT License, like
  the code. The pages the wordmark was chosen from are kept in
  `assets/brand/explorations/`.
- The social preview is a card: the lockup, what nixkeeper watches, and the
  page (`scripts/social-preview.html`, rendered by `nix run .#screenshots`).

### Changed

- The page's statuses use the identity's colours: up to date in Zambian
  Green, outdated in Persian Orange, failed and vulnerable in Norwegian Pink.
  Dots use the brighter tint, text a darker one, which is easier to read than
  before on both themes. Can't update, marked broken and a failed or
  unfinished build have their own Indian Gold instead of sharing outdated's
  colour. "On master" is in nixkeeper's violet instead of GitHub's purple,
  and open update PRs in the identity's green.
- Links and key UI on the page (focus outlines, active filters) are in
  nixkeeper's violet, from the brand's colour tokens, which the page now
  loads (`docs/tokens.css`).
- The docs call the frequent checks "about hourly": GitHub runs scheduled
  workflows on a best-effort basis, so they can be a few hours apart.

### Fixed

- On narrow tables, a package's status dot could end up on a line of its
  own, above the name; it now stays beside the name, and only the platform
  tags wrap.

## [0.5.0] - 2026-09-30

### Added

- Update checks for unstable versions (`github` + `branch` in
  `package-lists/update-checks.nix`): for a package whose nixpkgs version is
  `…-unstable-YYYY-MM-DD`, the commits since then on the branch it follows.
  Repology can't tell: it only tracks releases, and marks unstable versions
  "untrusted". The package counts as outdated once one of those commits has
  waited 90 days; `outdatedAfter = { days = …; commits = …; }` changes that
  per package (whichever comes first; `null` turns one off). Until then, the
  details list the newer commits as not counted yet. First one: stepmania
  (its `5_1-new` branch).
- Ignore rules for update attempts (`package-lists/ignored-updates.nix`): a
  version nixpkgs-update tried and failed that shouldn't count, such as one
  upstream never really released. Its failure shows as superseded, with the
  rule's reason; a failure at any other version still counts. The sync notes
  when a rule no longer matches the bot's latest attempt. First one: xskat's
  4.0-9.
- The build panel says which version last built on a failing platform, with
  a link to that build, next to the version that fails ("failed at 1.2.4 ·
  last succeeded at 1.2.3"). When both are the same, the version didn't break
  it; something else did (a dependency, the toolchain). Platforms that didn't
  build because of a dependency, or didn't finish, now show when they last
  succeeded too.
- The page links to nixkeeper's repository ("source and how it works") and
  to what its statuses and badges mean in its footer, and a copy of nixkeeper
  on GitHub Pages also links to its own package lists.
- The page has a description, for search engines and link previews.
- The README explains how to set up a dashboard of your own ("Track your own
  packages"), with screenshots of the page. How the code is laid out, the
  commands, and how changes and releases happen moved to
  `CONTRIBUTING.md`.
- The README explains how nixkeeper works (with a diagram) and how to read
  the page: every dot, badge and column state. `DATA.md` describes the data
  files, field by field, and `CONTRIBUTING.md` maps the code.
- Issue forms: "Track a package" and "Something looks wrong".
- A security policy (`SECURITY.md`): report vulnerabilities privately
  through GitHub's private vulnerability reporting.
- Dependabot (`.github/dependabot.yml`) proposes updates to the actions the
  workflows use, weekly.

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

[unreleased]: https://github.com/iedame/nixkeeper/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/iedame/nixkeeper/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/iedame/nixkeeper/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/iedame/nixkeeper/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/iedame/nixkeeper/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/iedame/nixkeeper/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/iedame/nixkeeper/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/iedame/nixkeeper/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/iedame/nixkeeper/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/iedame/nixkeeper/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/iedame/nixkeeper/releases/tag/v0.1.0
