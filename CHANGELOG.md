# Changelog

Notable changes to nixkeeper. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0, a minor bump means new
features).

The version lives in `pyproject.toml`; `flake.nix` reads it from there.

## [Unreleased]

### Added

- Which dependency failed, from nixkeeper-hydra's digest (which reads each
  dependency-failed build's page on Hydra, as zh.fail does): a build that
  didn't build because a dependency failed says "blocked by" it, linking
  its package; the list shows those packages as "blocked" (amber, not
  counted as failed: before, "none reported"); and the overview lists the
  failing packages blocking the most others, in all of nixpkgs. In the
  data: `blockedBy` on such builds, `blockers` in `index.json`
  (`docs/data.md`).
- Marks on the overview's trends: each merge of staging-next into nixpkgs
  master (mass rebuilds: failing builds jump for days after), from GitHub's
  search; each nixkeeper update a sync ran; and each change in how
  nixkeeper counts (`COUNTING_CHANGES`, the first being 0.12.0's older
  versions kept), on the day it first ran. Named and dated under the
  cards; in `history.json` as `events` (`docs/data.md`).
- `nix run .#start-runs`: starts an instance's runs through GitHub's API,
  hourly from a machine that's always on (a nix-darwin agent or a NixOS
  timer, in `docs/all-packages.md`), since GitHub's schedule skips runs
  when it's busy. The community instance's daily sync and digests by
  default; a fork's daily sync with `NIXKEEPER_START_REPO` and
  `NIXKEEPER_START_DIGESTS=` (it reads iedame's digests). The daily sync can be started with `if_older` (only when the last
  sync is older than that many hours), and its 06:00 run now stops when
  the last sync is under 12 hours old: started both ways, it syncs once.
- While nixkeeper-updates' digest is still reading nixpkgs-update's past
  attempts (a backfill), the Update failures card says how many are to go:
  update failures that were there all along keep turning up, so it rises
  without anything breaking.
- A "blocked" filter (`?filter=blocked`): packages with a build Hydra
  didn't try because a dependency failed, which no other count has (they
  aren't failing themselves). A count at the top when there are any; with
  every package, a tile in each list, and a view of them all
  (`?view=blocked`, `views/blocked.json`) that the overview's "Blocking the
  most" opens ("Show all"). Its count is now every blocked package's,
  whether nixkeeper-hydra has read which dependency it was yet or not.
- Build failures by platform: the overview's card says how many fail on
  Linux and on macOS (each Hydra system on hover; `buildFailuresOn` in
  `index.json`), and every list can be narrowed to one platform under its
  counts or tiles ("On Linux / macOS", `?platform=`), as a row's platform
  tag already did: build failures on macOS are a link now.

- nixpkgs-update attempts that ended "other" (15% of them) now say what
  happened, with the log's own line (parser 4, so every log is read again):
  `branchExists` (the bot already pushed that update to its branch: its PR
  is open or on its way), `skipped` (the bot passes the package over on
  purpose: it opts out, GNOME's release cycle, too many rebuilds, ...;
  "skipped" in the list), and, for `noChange` and `cantUpdate`, why
  (nothing newer by Nix's version order, the same hashes, the source URL
  unchanged). A request that failed (GitHub answering 500, say) is a
  failure, its excerpt the host and the answer, not the request's dump.
  nixpkgs-update's own messages that end an attempt are read too (as its
  source writes them, checked against r-ryantm-orbit's list): too many open
  PRs (`prExists`), no rewrites performed, the same revision or
  dependencies' hash, edits that rebuild nothing (`noChange`), no
  `version` attribute (`cantUpdate`), and its checks of a build that went
  wrong (`failed`).

- When nixpkgs-update will try a package again, and what it would update
  it to, from the bot's queue (nixkeeper-updates' copy of it): "Next
  attempt expected around Oct 12, from its queue: it would update it to
  4.22.7 (GitHub release · Repology)" in the update panel, or "not in the
  queue" when it sees nothing to update to; and in the list, a robot's
  head joined to the update cell ("queued" to screen readers; green when
  to the newest version and its last attempt didn't fail: its PR should
  follow; amber when the bot will try but it's unsure, its last attempt
  having failed, another version, or an outdated package's updateScript
  deciding the version), which opens that panel too. Rows have it as
  `queued` (`docs/data.md`); the sources panel says when the queue is from.

- The dashboard is at https://nixkeeper.com/, served from Cloudflare (a
  Worker serving static assets): the page and its data as one site, from
  Cloudflare's edge, instead of the data from raw.githubusercontent.com.
  The data workflows publish it there when the page or the data changed,
  for an instance with a Worker set (`CLOUDFLARE_WORKER`;
  `docs/all-packages.md`); the
  data branch stays the syncs' own copy, and GitHub Pages the page of every
  other instance. GitHub Pages' workflow also writes where the data is into
  the page, so one on a custom domain finds it as on github.io.

### Changed

- With every package, failing is split in two on the overview and in a
  list's tiles: **build failures** (a build of its own failing) and
  **update failures** (nixpkgs-update's attempts failing), each its own
  card, trend and filter (`?filter=builds`, `?filter=updates`;
  `?filter=failed` still shows both). The history records both
  (`buildFailures`, `updateFailures`), and a sync adds them to the day
  before's point from that day's manifest, so the split trends start at
  once.
- The overview's trends show from the second daily sync, not after a
  week; until there's a week, each card's change is since the first sync
  (hover it for which).
- `nix run .#screenshots` takes every package's overview too, when the data
  is a community instance's: the same shots, starting with `overview-`
  (the desktop ones taller, no panel; the social preview's card says
  "every nixpkgs package"), beside the list's, which a run with a
  list-based instance's data retakes as before. `--data` can be a local
  folder too, served next to the page.

### Fixed

- The page for screen readers, phones and low vision (a pass before the
  community page is announced):
  - muted text (labels, dates, zeros, headers) is now 4.5:1 against its
    background in all four palettes (it was 2.6 to 4.4:1);
  - the overview's sections and cards are headings, and each list has one
    (its name), to move between with a screen reader;
  - a package's status dot says what it means, the cards' changes say "up"
    or "down" and since when, and how many packages a filter, tile or
    search leaves is announced;
  - on touch screens, everything tapped is at least 24px each way (the
    platform tags, the ✕ back from a list, the help button, the narrowing
    buttons and pickers, PR badges, "Show all"), and the header's buttons
    no longer stick out past the screen's margin;
  - the build, update and platform buttons have the page's focus ring.
- The list no longer widens the page past the screen (scrolling it
  sideways, the last column cut off) for a long package name or a long
  version with badges beside it: a name wraps after a dot or at a hyphen
  (`home-assistant-custom-components.` / `homematicip_local`), and the
  badges under each other. With every package, "needs attention" was
  1,400px wide in a 1,280px window.
- Which dependency failed was left out for every build whose last success
  nixkeeper-hydra's digest doesn't know (one that never built, say): with
  every package, most of them (the overview counted 61 blocked packages
  instead of about 580), and with lists, every one asked of Hydra (which
  doesn't say). It's kept now, and added to Hydra's answer for the same
  build.

### Removed

- The data's first format is no longer written: no `packages` in
  `index.json` and no `<project>.json` files (the shards have had the same
  since 0.12.0), so `data/` is smaller (a few files instead of one per
  Repology project) and syncs and the hourly checks write less. A page from
  0.11.0 or before can't show the new data: update it with the data (the
  modules and the GitHub workflows do). The page no longer reads the first
  format either, and says so for data from 0.11.0 or before; the sync
  still reads it, so upgrading from 0.11.0 keeps the last run's data, and
  rewrites it in the second format (`docs/data.md`).

## [0.12.0] - 2026-10-06

nixkeeper can now track **every nixpkgs package**, for a community
instance (`NIXKEEPER_ALL_PACKAGES=1`, `allPackages` in the modules): about
126,000 rows, read in bulk from three digests (Hydra's builds, Repology's
versions, nixpkgs-update's attempts), with a page that starts from an
overview of all of nixpkgs. Instances that track their lists, as before,
get the new data format, paging, teams, failing ages, the narrowing
filters and the sources panel; their page looks as it did otherwise.

### Added

- Every package: `NIXKEEPER_ALL_PACKAGES=1` (a repository variable on
  GitHub, `allPackages` in the modules, `sync --all-packages`) tracks every
  nixpkgs package, not only the lists', for a community instance
  (`docs/all-packages.md`). The lists' packages are read as always and are
  the only ones in the status issue; the rest only from the digests and
  bulk listings, with nothing asked per package (nixpkgs-update's attempts
  from nixkeeper-updates' digest, above). Generated sets (R, Haskell,
  Emacs, Typst, TeX Live, SBCL) are pending: only Repology's versions and
  Hydra's builds. The data then has views (needs attention, marked broken,
  per maintainer, team, list and set), a name index, counts and their
  history, instead of one summary of every package
  (`docs/data.md`). The page then starts from an overview of all of
  nixpkgs (fully checked, and in generated sets): cards for the outdated,
  failing, vulnerable and broken packages with their weekly change and
  trend (`history.json`, from the first sync on), a search with a team
  picker (its matches in place of what follows, while searching), the
  newest and longest-standing build failures, outdated packages and update
  failures, and the generated sets with how much of
  each is marked broken or failing; each opens a list (what needs
  attention, marked broken, a maintainer's, a team's, a generated set's,
  one package's), whose tiles count and filter it. Visitors can keep their
  own GitHub handle and team (in their browser) for "Your packages" and
  "Your team"; the instance's own lists open by address only. A search
  also lists matching names beyond the list shown.
- A second format for the data, beside the first: `summary.json`, a short
  entry per package with what the page's list needs (about a third of
  `index.json` today), and `rows/<n>.json`, the packages in full with their
  Repology data, split by a hash of the name. `index.json` says
  `"format": 2` and how many packages and shards there are. The first
  format is still written, unchanged (`docs/data.md`).
- The page reads the second format when the data has it: the list from
  `summary.json` (about a third of the download), and a package's full row
  from its shard when one of its panels opens (once a shard). It still reads
  the first format, so it works with data from before.
- The list is paged: 200 packages at a time, most in need of attention
  first, with page links under it and `?page=` in the address. Drawing stays
  fast however many packages there are; changing a filter, the search or the
  order goes back to the first page.
- Packages' nixpkgs teams (`meta.teams`): in the data (`teams`), in the
  details panel, and as a filter (`?team=gaming`, or a team's name in the
  panel).
- How long a package has been failing: `failingSince` (its builds, since
  their last success when first seen) and `updateFailingSince` (its update
  attempts), carried from sync to sync like `outdatedSince`; a red age tag
  after the name, and failing packages listed longest first.
- Packages nixpkgs marks broken show "marked broken" even when Hydra has no
  job for them (`markedBroken`, from the package index's `meta.broken`):
  until now, a broken package with no Hydra job (as hackage2nix makes them)
  only said "not built by Hydra".
- nixpkgs-update's attempts from
  [nixkeeper-updates](https://github.com/iedame/nixkeeper-updates), a digest
  of the bot's latest attempt at every package (its log read with
  nixkeeper's own rules, every 3 hours, from the bot's state), instead of
  reading each package's logs; still read per package when the digest
  hasn't read the latest attempt, or isn't current
  (`NIXKEEPER_UPDATES_DIGEST`). With every package, every package gets its
  attempt this way.
- Where the data is from: "checked … ago" on the page opens each source's
  time (the daily sync; the Hydra evaluation its builds are from and when
  it was read; when Repology's versions and nixpkgs-update's attempts were
  read, and how many attempts are still to read; the nixpkgs commit), and
  says when the sync didn't use a digest (too old, or unreadable) and why.
  In the data: `sources` in `index.json` (`docs/data.md`).
- Narrowing any list, together with its other filters: without
  maintainer, not marked broken, not fixed on master yet (an outdated
  package whose update is merged, waiting for nixos-unstable), and older
  than a month, 6 months or a year (failing or outdated for that long).
  Under the counts, or with every package under a list's tiles; in the
  address as `?refine=` and `?age=` (`docs/reading-the-page.md`).
- Recently fixed, with every package: each daily sync notes what's fixed
  since the one before (a build that works again, a package updated, a
  nixpkgs-update failure cleared), only with something showing it (Hydra's
  success, a new version in nixpkgs, a newer attempt), so a late source or
  a change in how nixkeeper counts never looks like a wave of fixes. The
  last 30 days' in `history.json` (`fixed`); the overview shows the last
  week's, newest first.
- Maintainers, with every package: `maintainers.json` (every maintainer,
  with their packages, outdated and failing counts); "browse every
  maintainer" on the overview (`?view=maintainers`), by handle, the search
  narrowing them; and typing `@` and part of a handle suggests the
  maintainers whose handle matches.

### Changed

- An older version nixpkgs keeps on purpose beside a newer one under
  another attribute (Repology's "legacy": `tracy_0_11` beside `tracy`,
  `gnumake42`, `php82Extensions`, older kernels' modules) isn't counted as
  outdated anymore: it's shown as an "older version", with the newer one
  named (`keptBeside`). It's still outdated by a newer release in its own
  series (the worked-out update checks look there), and a beta behind the
  newest betas still is. On 2026-10-06's data, about 1,650 fewer outdated
  packages (16%): the Outdated trend steps down once, at the first sync
  with this. The community up-to-date rules for `tracy_0_11` and
  `tracy_0_12` are gone, as this covers them.
- The daily sync workflow runs again at 14:00 UTC as a catch-up: it only
  syncs if the last sync is over 20 hours old (GitHub skipped or badly
  delayed the 06:00 one), and otherwise stops at once.
- The files in `data/` are written as compact JSON, without indentation:
  about a third smaller for the browser to read (a few percent smaller to
  download, as servers send it gzipped). The data is the same: tools that
  parse JSON aren't affected.
- Dates that are the sync's own time are left out of the data: a package's
  `countedAt`, its update check's `checkedAt` and each build's `checkedAt`,
  when they equal `checkedAt` in `index.json` (a missing one means that).
  A package nothing new happened to now reads the same from one sync to the
  next (222 of 224 rows on today's data), instead of every row changing
  every day.

### Fixed

- A project's attributes split into rows by version counted every one
  after the first as a devel variant, older series too (`gnumake42`,
  `php82Extensions`, `flatbuffers_23` had a "devel" badge and were compared
  with devel versions). Now only one newer than the stable one, or named
  for one (`-devel`, `-beta`, `-unstable`, ...), is.
- With every package, an hourly check that changed something took half an
  hour or more to write it (an Edge release did, and two runs were stopped
  after 22 minutes): it read each row's Repology entries on its own,
  reading and parsing a whole shard again for nearly every one of about
  126,000 rows. It now reads each shard once: about 20 seconds in all.
- A site sending its answer a little at a time could hold a run for hours:
  a request's timeout only bounded each wait for the next bytes. Now a
  whole answer has a minute to arrive (5 for a digest's download), or the
  request has failed, is retried, and the package keeps its previous result
  as when a site is down. The data workflows also have time limits (20
  minutes hourly, an hour daily), so a run that hangs can't hold the data
  branch, which the other one waits for, up to GitHub's default of 6 hours.

## [0.11.0] - 2026-10-05

Ready for big lists: Hydra's builds, Repology's data and GitHub's PRs and
issues now come in bulk, at about the same cost whatever the lists' size (a
daily sync of 1,500 packages is estimated at about 12 minutes, down from
about 45; 241 take under 4); update checks are worked out from nixpkgs for
packages without a rule; and team members can find their own packages on the
page.

### Added

- Update checks worked out from nixpkgs itself, a first step towards
  relying less on Repology. A package without an update check of its own
  (or a community rule) that nixpkgs fetches from a GitHub tag is checked
  against that repository's tags, in the scheme its own tag shows (`v1.2.3`,
  `release-1.2.3`, ...), plain versions only, shaped like nixpkgs' (a dotted
  version doesn't take a lone number such as a `20240214` date tag) and, for
  a versioned attribute (`tracy_0_11`, `gcc13`, `python313`), in its series
  only: a newer one there makes it outdated, as any update check's does, so
  new releases show before Repology counts them. On by default;
  `workedOutChecks = false;` in the lists (`lists.workedOutChecks` in the
  modules) leaves those packages to Repology. One that fails (a renamed
  repository, no matching tag) leaves its package to Repology without a
  warning: nobody wrote it to fix. A rule of your own or the community's
  wins, for a package these get wrong (Wesnoth's stable series has one now).
  Each daily sync's log compares them with Repology and with the packages'
  rules, in a collapsed group. They cost one nixpkgs evaluation (seconds)
  and one GitHub request per 50 repositories.

- Search by maintainer: `@handle` in the search box lists the packages
  nixpkgs gives that maintainer (their GitHub handle, in any case), and
  `@none` those with no maintainer, so `?q=@yourhandle` is a link to a team
  member's own packages. The details panel lists a package's maintainers,
  each a search for theirs and a link to their GitHub profile. Rows get
  `maintainers` from the nixpkgs index the sync already reads (no new
  requests); the page finds them after the first sync with this version.

- The details panel lists `nixkeeper` first among the repositories a
  package is compared against, with the version its update check found
  (highlighted when it's newer than nixpkgs', as the others are); hover it
  for where that came from.

### Changed

- Hydra's builds come from [nixkeeper-hydra](https://github.com/iedame/nixkeeper-hydra)
  first: a digest of every job in Hydra's newest evaluation of nixpkgs
  master, kept up to date hourly by its own workflow. One download (about
  2.6 MB) answers most jobs, every day, instead of a request or two per job:
  a new build failure shows up the next day for every package. Hydra is
  still asked about the jobs the digest can't answer (missing from it, not
  built yet, or failing with no known last success), and about every job
  when the digest isn't current (from an older evaluation and over 12 hours
  old) or can't be downloaded. `NIXKEEPER_HYDRA_DIGEST` points elsewhere, or
  empty turns it off. Hydra's newest evaluation is read from its list of
  evaluations, not from `latest-eval`, which is the newest whose builds have
  all finished.

- Repology's data comes from [nixkeeper-versions](https://github.com/iedame/nixkeeper-versions)
  first: a digest of every nixpkgs project on Repology, which its own
  workflow reads in bulk daily, as nixpkgs-update does (outdated projects
  every day, the rest every week; about 200 requests a day for all of
  nixpkgs, within Repology's API rules). One download (about 12 MB, read a
  project at a time, so little memory) answers most tracked packages: a
  sync of 241 packages looked up 2 of them. Repology is still
  asked about packages missing from the digest (new in nixpkgs) or with
  another version there than the channel's (changed since), and about
  every package when the digest is more than 36 hours old or can't be read.
  `NIXKEEPER_VERSIONS_DIGEST` points elsewhere, or empty turns it off.

- Open PR and issue counts and update PRs come from bulk listings instead
  of two or three GitHub searches per package: every open nixpkgs PR and
  issue (about 120 GraphQL requests, 100 of each per request) and the PRs
  merged into master since the channel's commit (about 10 more), however
  many packages are tracked, with each package's counts and update PRs
  found in the titles locally. A sync of 241 packages made about 300
  searches before. Counts match GitHub's title search (whole words, plurals
  included, checked side by side: 126 of 128 packages agreed, and every
  update PR); its deeper stemming isn't copied, so a package named like an
  English word can count a few fewer ("trigger" doesn't count "triggered").
  Every package is counted daily. When a listing fails, or there's no token
  for it, the sync searches per package; the hourly update-PR check, for a
  few packages, still searches.

- When nixkeeper asks per package (the digests or listings aren't
  available, or for what they can't answer), it asks less about what's
  quiet, as nixpkgs-update spreads its queue: a Hydra job that built fine
  with nothing pending, an update check that found nothing newer (unless
  it's `frequent`), a Repology lookup for a package that's up to date, not
  vulnerable and unchanged in nixpkgs, and the PR and issue searches of a
  package with none open, each every 3 days (a third each day) instead of
  daily. Anything failing, outdated, newly changed, with an update PR, or
  whose lookup failed is still asked daily, and so is everything the first
  time. Each result records when it was read (`builds[].checkedAt`,
  `upstream.checkedAt`, `repologyCheckedAt`, `countedAt`), and the details
  say how old it is when it isn't from today. An update check also runs
  again at once when its rule is edited (`upstream.rule`, a fingerprint of
  it).

- New sizes: the list check warns from 1,500 packages instead of 500, and
  the sync refuses to start above 5,000 instead of 2,000 (`maxPackages` to
  go beyond). The estimate a sync starts with is measured anew: about 150
  requests and 2 minutes whatever the lists' size, then per package about
  0.3 requests and half a second on a typical day, about 3 and 3 seconds the
  first time it's synced (1,500 packages: about 12 minutes a day), and it
  counts the packages new to this sync. On GitHub Actions it warns when a
  sync may outlast the job's 6 hours (about 8,000 new packages at once),
  which would publish nothing: big lists are best added in stages.

- The daily sync asks Hydra in the background from the start, while it
  asks the other sources, instead of after them. Each server is still asked
  one request at a time.

- Fewer requests to the sources, for the same results:
  - Repology: a package looked up directly is looked up by the project the
    last sync found for it, one request instead of two (asking by attribute
    is answered with a redirect to the project). If Repology has moved the
    package to another project, it's looked up by attribute as before.
  - nixpkgs-update's logs: the log site's index (one request, compressed)
    says when each package's logs last changed, so a package whose logs
    haven't changed since the last sync isn't listed again, and one with no
    logs isn't asked about. For 72 attributes, a sync made 3 requests
    instead of at least 72, with the same results.
  - Update checks against a web page ask its server to send it only if it
    changed since the last check (the page's `ETag` and `Last-Modified`),
    and keep what they found when it didn't: the hourly microsoft-edge
    check read a 1 MB file each time, now only when Edge has changed. A rule
    whose page or pattern changes reads the page whole again
    (`upstream.page` records what's sent).
  - Update checks against GitHub ask about tags and branches 50
    repositories per request, and a request that fails only affects its
    own 50.

- Update checks against web pages ask each site at most once a second, and
  take turns between sites, so many rules on one site (PyPI, a vendor's)
  don't arrive back to back. The other sources already paced themselves.

- The page stays responsive with big lists. With 3,000 packages, redrawing
  the list on a phone or tablet takes about a third of the time it did
  (cards off screen are only laid out when scrolled near), searching redraws
  once typing pauses instead of at every key, and a row's panel is only made
  when it's first opened. On wide screens, a table of that size still takes
  about half a second to redraw on a fast computer: about a quarter of a
  second at 1,500 packages.

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

- For readers of the data (`docs/data.md`): rows have new fields,
  `maintainers`, `repologyCheckedAt` and `countedAt`; builds have
  `checkedAt`; update checks have `rule`, `page` and `inferred` (worked out
  from nixpkgs). `repoCount` now counts repositories
  (below).

### Fixed

- Repology is asked at `repology.org` only: its mirror `repology.amdmi3.ru`,
  which nixkeeper fell back to when `repology.org` failed, is discontinued
  on 2026-10-09. A failing `repology.org` is retried as before, and
  `REPOLOGY_BASE_URL` still sets another address.

- The NixOS module always puts Nix on the jobs' path: the sync evaluates
  nixpkgs, for worked-out update checks and where nixpkgs marks packages
  broken. Before, with lists set in the configuration and no community
  rules, it had no Nix, and skipped `meta.broken` with a warning.

- The package lists' check (`nix flake check`) accepted an entry that names
  a set of packages rather than a package (`cataclysmDDA`, which holds
  `stable`, `git`, ...): it passed CI, then the sync couldn't find it and
  the page showed a list problem. Entries, update checks and rules now have
  to name a package, and a set of packages is reported as such.

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

[unreleased]: https://github.com/iedame/nixkeeper/compare/v0.11.0...HEAD
[0.12.0]: https://github.com/iedame/nixkeeper/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/iedame/nixkeeper/compare/v0.10.0...v0.11.0
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
