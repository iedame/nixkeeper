# The data

Everything the page shows comes from plain JSON files, which each sync
rewrites and commits to the `data` branch, under `data/`. That branch is
always `main` plus one commit with the latest data: each run replaces it, so
it keeps no history.

- `index.json`: the sync's details (when, which version, list problems)
  and the counts of rows and shards
- `summary.json`: a short entry per row, with what the page's list needs
  (below)
- `rows/<n>.json`: the rows in full, with their Repology entries, in shards
  (below)

This is the data's second format, which lets the page load only what it
shows. The first (0.11.0 and before; written beside the second until
0.13.0) had every row in `index.json` (`packages`) and each Repology
project's entries in a file of its own (`<project>.json`): the page no
longer reads it, and the next sync after upgrading rewrites it.

On GitHub they're at
`https://raw.githubusercontent.com/<owner>/<repo>/data/data/index.json`.

Fields are only present when they have something to say: a field missing
from a row means none (no open update PR, never outdated, ...). Dates are ISO
8601 in UTC (`2026-09-30T06:00:00+00:00`), or a plain day (`2026-09-26`) where
the source only has that. New fields may be added; existing ones change only
with a note in the [changelog](../CHANGELOG.md).

The files are compact JSON (no indentation) with keys sorted, so a file
whose data didn't change keeps the same bytes. For the same reason, three
dates are left out when they're the sync's own (`checkedAt` in
`index.json`): a row's `countedAt`, its update check's `checkedAt` and each
build's `checkedAt`. Each is always there otherwise, so a missing one means
"at `checkedAt`"; a package nothing new happened to then reads the same from
one sync to the next. Format them to read them by
hand (`jq . index.json`).

## `index.json`

```json
{ "format": 2, "checkedAt": "2026-09-30T06:00:00+00:00", "version": "0.13.0",
  "packageCount": 241, "shardCount": 1 }
```

`format` is the data's format (2; missing in data from before). `version`
is the nixkeeper that ran the last full sync (the page shows it at the
bottom). `checkedAt` is when the last full sync ran (the hourly checks update
single rows without changing it). `packageCount` is how many rows there are,
`shardCount` how many shards hold them.

`listProblems`, only when there are any, lists mistakes the sync found in the
package lists, as sentences: a maintainer handle no package lists, an extra
package nixpkgs doesn't have, an update check, ignore or up-to-date rule for
a package that isn't tracked, or 1,500 packages or more (the cost of a sync).
The page shows them above the table. `page`, only when the lists set it,
holds the page's settings: `{ "theme": "catppuccin" }` is
its default palette.

`sources` says where the last full sync's data came from, by source:
whether it was used (`used`), and if not, why (`why`: too old, or couldn't
be read; the sync then asked per package instead, an old versions digest
answering where Repology couldn't). `repology` is there only when lookups
failed: how many (`why`); those packages kept their last versions. `hydra` has the
evaluation its builds are from (`eval`) and when nixkeeper-hydra read it
(`at`); `versions`, when nixkeeper-versions last read the outdated projects
(`at`); `typst`, when nixkeeper-versions last read Typst Universe's index
(`at`) and how many packages it has (`packages`; not used, Repology's
versions stay); `emacs`, likewise for the Emacs archives (`at`, and
`melpa`, `melpaStable`, `nongnu`, `gnu`: how many packages each has);
`cran`, likewise for CRAN and Bioconductor (`at`, `biocVersion`: the
release nixpkgs pins, and `cran`, `bioc`, `annotation`, `experiment`: how
many packages each index has); `stackage`, likewise for Stackage LTS (`at`, `snapshot`: its newest,
`nixpkgs`: the one nixpkgs follows, `packages`: how many it pins);
`branch:haskell-updates`, when nixkeeper-hydra last read the
haskell-updates jobset (`at`), which evaluation (`eval`) and how many jobs
(`jobs`; not used, rows have no `branch`); `updates`, when nixkeeper-updates made its digest (`at`) and how
many attempts it hasn't read yet (`pending`); `queue`, when the bot's queue
was made (`at`) and how many days it takes to go round (`cycleDays`);
`nixpkgs`, the channel's commit (`revision`); `github`, whether the open PRs
were listed in one go.
A source that's turned off isn't there; data from before 0.12.0 has none.
The page shows them under "checked … ago".

```json
"sources": {
  "hydra": { "used": true, "at": "2026-10-05T13:41:00+00:00", "eval": 1829853 },
  "versions": { "used": false, "why": "too old", "at": "2026-10-03T04:20:00+00:00" },
  "updates": { "used": true, "at": "2026-10-05T12:30:00+00:00", "pending": 1204 },
  "queue": { "used": true, "at": "2026-10-05T12:15:00+00:00", "cycleDays": 10.3 },
  "nixpkgs": { "used": true, "revision": "8f3a1c2…" },
  "github": { "used": true }
}
```

## `summary.json`

```json
{ "packages": [ ... ] }
```

One entry per row, sorted by name: the row (below) without what only its
details show (`dataFile`, `homepage`, `repoCount`, `repologyCheckedAt`,
`source`), its `queued` with only the versions and whether the bot runs its
updateScript (`{ "to": ["4.22.7"], "script": true }`, when there's either),
its builds with only `status` and `system`, its `update` with only
`outcome` and `failedBecause` (still `null` when the bot never tried, missing when it isn't in
nixpkgs), and its `upstream` with only `version`, `newer`, `community` and
`inferred`.

## `rows/<n>.json`

```json
{ "packages": [ ... ] }
```

The rows in full, sorted by name, each with its Repology project's entries
in `repology`: one entry per repository and package, with only what
nixkeeper reads (`repo`, `srcname`, `version`, `status`, and `vulnerable`
when flagged), each once; missing when there are none. Rows
are spread over `shardCount` shards (a power of two, about 500 rows each) by
a hash of their name: a row is in shard `crc32(name) % shardCount` (CRC-32
of the name's UTF-8 bytes, as zlib computes it), so a new package changes
only its own shard.

## Every package

With [every package](all-packages.md) tracked, `index.json` says
`"allPackages": true` and there's no `summary.json` (every package's entry
would be too much to load; the shards' entries are, for packages not on the
lists, nixpkgs' own and those of the 8 newest other repositories). Instead:

- `counts` in `index.json`: `tracked`, `outdated`, `failed` (failing in
  any way), `buildFailures` (a build of its own failed), `updateFailures`
  (nixpkgs-update's attempts failing), `vulnerable`, `broken` (marked
  broken), `waiting` (outdated, the
  update merged on master) of the rows not in a set updated in bulk;
  `inSets`, how many are (`pending` before 0.14.0); and
  `failingBuilds`, every Hydra job of every row that didn't build (failed,
  a dependency failed, or unfinished), on every platform; and
  `buildFailuresOn`, the `buildFailures` by where they fail: `linux`,
  `darwin` and each Hydra system (`x86_64-linux`, ...), a package counted
  where it's available only, as the page's platform filter does;
- `highlights` in `index.json`: for `failing` (builds), `outdated` and
  `updateFailing`, of the rows not in such a set, `{ "count", "newest", "oldest" }`:
  how many there are, and the 8 most recent and 8 longest-standing, each
  `[name, since, status]` (from `failingSince`, `outdatedSince`,
  `updateFailingSince`; `status` as in `names.json`);
- `blockers` in `index.json`: the failing dependencies that stop others'
  builds, of every row (in sets too, as zh.fail counts them): how many
  there are (`count`), how many packages have a build they stopped
  (`packages`, as many as `blocked.json` has, whether nixkeeper-hydra has
  read which dependency it was yet or not), and the 8 that stop the most
  (`top`), each `[name, row, packages, builds]`;
- `views` in `index.json`: how many rows `attention`, `broken` and `blocked` have, the `teams` and
  `lists` with their counts (`{ "Gaming": 12, ... }`), and the `sets`
  with how many packages each has, how many of them are outdated (from
  0.14.0; `onBranch`: of those, how many are already updated on the
  branch that updates the set before master, haskell-updates), fail, and
  nixpkgs marks broken; for R, `archived` (no longer on CRAN or in
  Bioconductor) and `archivedUnmarked` (those not marked broken)
  (`{ "haskellPackages": { "packages": 19423, "outdated": 1083, "failed": 83, "broken": 7600 }, ... }`);
- `profiles` in `index.json`: what updates each set updated in bulk,
  `{ "rPackages": { "name": "R", "updatedBy": "the CRAN and Bioconductor
  import (generate-r-packages.R)", "short": "CRAN import", "link": ... },
  ... }` (`SET_PROFILES` in `config.py`);
- `views/`, each `{ "packages": [ ... ] }` of summary entries, sorted by
  name: `attention.json` (failing, outdated or flagged vulnerable, not in a
  set updated in bulk), `broken.json` (marked broken, not in such a set),
  `blocked.json` (a build not tried because a dependency failed, in such
  sets too),
  `maintainer/<handle>.json` (the handle in lowercase; `none.json`: no
  maintainer, not in such a set), `team/<slug>.json` and `list/<slug>.json` (the
  name in lowercase, each run of other characters than letters and digits
  a `-`: `Security review` is `security-review`), `set/<name>.json` (a
  set's rows);
- `history.json`: `{ "points": [ { "day", "tracked", "outdated", "failed",
  "buildFailures", "updateFailures", "vulnerable", "broken" }, ... ],
  "fixed": [ ... ] }`. `points`: the counts of the rows not in a set at each
  daily sync (the last 365 days; a second sync the same day replaces the
  first), the overview's trends. Points from before 0.13.0 have `failed`
  only; a sync adds `buildFailures` and `updateFailures` to the previous
  day's from that day's manifest.
  `fixed`: what each daily sync found fixed since the one before, the last
  30 days, each `{ "at", "name", "kind", "from"?, "to"? }`, of the rows not
  in a set, and only with something showing it: `build` (it was failing; no
  build fails now, and Hydra has a success), `update` (it was outdated; it
  isn't, and nixpkgs' version changed: `from` and `to`), `bot`
  (nixpkgs-update's attempts were failing; they aren't, and its attempt
  changed: a newer one, or superseded). A source that's late, or a change
  in how nixkeeper counts, so doesn't look like fixes. `events`: what
  marks the trends, the last 365 days: `{ "day", "kind": "staging-next",
  "pr", "title" }` for each merge of staging-next into master (mass
  rebuilds: failing builds jump for days after; asked of GitHub's search
  each daily sync, the last 30 days', kept once each), and `{ "day", "kind":
  "nixkeeper", "version", "from" }` when the sync ran a new nixkeeper
  version, and `{ "day", "kind": "counting", "text" }` for a change in how
  nixkeeper counts (`COUNTING_CHANGES` in `config.py`), on the first day the
  sync ran with it (a change can step a count overnight);
- `fixed` in `index.json`: of those, the last 7 days' (`days`): for
  `build`, `update` and `bot`, `{ "count", "newest" }`, the 8 newest each
  `[name, at, from, to]`;
- `maintainers.json`: `{ "maintainers": [ [handle, packages, outdated,
  failing], ... ] }`, every maintainer by handle (any case; as nixpkgs
  writes it first), with how many packages list them (in sets too)
  and how many of the rows not in a set are outdated and failing: the
  maintainers page, and suggestions for a search starting with `@`;
- `names.json`: `{ "names": [ [name, status], ... ] }` for every row, with
  its set as a third element when it's in a set updated in bulk. `status` is a letter as the
  page's dot: `f` failed, `m` outdated but merged on master, `o` outdated,
  `u` up to date, `n` can't be compared; then `v` when flagged vulnerable.

## A row

### What it is

| Field | Meaning |
|---|---|
| `name` | the row's name: its nixpkgs attribute (`wesnoth-devel`), or the list entry when nixpkgs doesn't have it |
| `attrs` | the nixpkgs attributes the row covers (variants sharing a version, like `heroic` and `heroic-unwrapped`) |
| `searchTerm` | what GitHub searches for its PRs and issues: the attribute, with versioned sets under the name nixpkgs titles use |
| `lists` | the lists it's on: `maintained` (found through a maintainer handle), then the named lists (`gaming-team`, ...) |
| `project`, `dataFile` | its Repology project, and the key its entries are kept under (a file-name-safe form of the project's name: its file in `data/` in the first format) |
| `platforms` | `{ "linux": bool, "darwin": bool }` from `meta.platforms`; `null` when nixpkgs doesn't restrict them |
| `homepage` | `meta.homepage` |
| `maintainers` | the GitHub handles in `meta.maintainers`, of all its attributes; `[]` when nixpkgs lists none (with a handle), missing when nixpkgs doesn't have it |
| `markedBroken` | `true` when nixpkgs marks one of its attributes broken (`meta.broken` in the package index, evaluated for x86_64-linux), even with no Hydra job to say so (a broken package often has none) |
| `teams` | the nixpkgs teams in `meta.teams` (`maintainers/team-list.nix`), of all its attributes, by their short name (`Gaming`, `Qt-KDE`); missing when it has none |
| `set` | with every package: the set updated in bulk (`haskellPackages`, ...) of a row no list has: counted on its set's line, without GitHub's counts ([every package](all-packages.md)); `index.json`'s `profiles` says what updates it. Data from 0.13.0 and before has `"pending": true` beside it |
| `branch` | for a row built on a branch that updates its set before master (haskell-updates, from nixkeeper-hydra): `{ "name": "haskell-updates", "version", "status", "build" }`, the branch's version, how its build went there (as `builds`' statuses) and the build. Counts nothing: the page says an update waits for the branch's merge, or a failure is fixed there, or that a package breaks when it merges |
| `lookupFailed` | `true` for a package Repology couldn't be asked about on this sync (down, most likely) with no earlier data: shown as not looked up, `nixStatus` `unlisted` |
| `unversioned` | with every package: `true` for a row of `darwin` or `freebsd`, not versioned software: its builds are what's checked |
| `unread` | with every package: the sources this sync didn't read for the row and kept as they were (`["update"]`: its nixpkgs-update attempt, which nixkeeper-updates' digest hasn't read yet) |
| `source` | where nixpkgs defines it, on GitHub at the channel's commit and line |
| `unfree` | `true` when every attribute is unfree (Hydra doesn't build those) |

### Versions (Repology, and nixkeeper's own checks)

| Field | Meaning |
|---|---|
| `nixVersion` | the version in nixos-unstable |
| `nixStatus` | Repology's status for it: `newest`, `outdated`, `devel`, `unique`, `legacy`, `untrusted`, `rolling`, `noscheme`, `incorrect`, ..., or `missing` when nixpkgs doesn't have it; with every package, `unlisted` for one Repology doesn't know (`nixVersion` is then nixpkgs') |
| `refVersion` | the newest version seen elsewhere (for a devel row, the newest devel one), or what nixkeeper's update check found, or what master has (`master`), whichever is newest |
| `refFromMaster` | `true` when `refVersion` is master's: newer than anything Repology or an update check knows of |
| `repoCount` | how many other repositories Repology compares it with (each counted once) |
| `devel` | a development variant of a split project: newer than its stable one, or named for one (`wesnoth-devel`, `_1password-gui-beta`); or a version Repology calls devel |
| `keptBeside` | for an older version nixpkgs keeps on purpose (Repology's `legacy`: `tracy_0_11`, `gnumake42`, `php82Extensions.zip`), the newer one beside it: `{ "attr", "version" }` |
| `feed` | when its versions are compared with its own source instead of Repology: `{ "name", "version", "released"?, "dated"?, "url" }`, its newest version there, the day it was published (when the source says), and `dated` when versions are a build's date and time (MELPA's `20251005.508`). `nixStatus` and `refVersion` are then from it. Typst packages, with Typst Universe: `outdated` or `newest` for a package's latest attribute (`typstPackages.cetz`), `legacy` for its other versions (`typstPackages.cetz_0_3_0`). Emacs packages, with the archive each comes from (`MELPA` for a MELPA version, else the first of `MELPA Stable`, `NonGNU ELPA` and `GNU ELPA` that has it, in nixpkgs' order); not the hand-written ones, the devel archives' versions or packages no archive has. Haskell packages nixpkgs pins to Stackage LTS, with that series' newest snapshot (`Stackage LTS 24`): also `snapshot` (`lts-24.62`), `followed` (the one nixpkgs follows, `lts-24.38`) and `heldBack` (Hackage's newer version, which Stackage holds back until its next series); the rest of `haskellPackages` keep Repology's verdict. R packages, with `CRAN` or the Bioconductor release nixpkgs pins (`Bioconductor 3.23`) |
| `archived` | `true` for an R package on neither CRAN nor the Bioconductor release nixpkgs pins any more (archived by CRAN, or dropped by Bioconductor); its status stays Repology's. nixpkgs marks most of those broken already |
| `nixVulnerable` | Repology flags `nixVersion` as vulnerable (its CVEs: `https://repology.org/project/<project>/cves`) |
| `outdatedSince` | when nixkeeper first saw it outdated; gone once it's caught up |
| `failingSince` | since when a build of it has been failing (its own build, not a dependency's): kept from sync to sync while it fails, gone once it doesn't; first seen, it's the failed builds' last success (the failing began after it), or then |
| `updateFailingSince` | since when its nixpkgs-update attempts have been failing, the same way; first seen, the failed attempt's day |
| `staleSince` | Repology couldn't be reached for it: the version data is from this time |
| `repologyCheckedAt` | when its Repology data was read: the day nixkeeper-versions' digest read it (daily for outdated projects, weekly for the rest), or when Repology was asked directly (daily while it's outdated, flagged vulnerable, changed in nixpkgs or new, otherwise every 3 days) |
| `upstream` | nixkeeper's own update check, when it has one (below): a rule of yours or the community's, or one worked out from nixpkgs |
| `upToDate` | an [up-to-date rule](community.md#up-to-date-rules-until-something-changes) applies: Repology gets `nixVersion` wrong, so `nixStatus` is `newest` and there's no `refVersion`. `status` is what Repology said, `newest` the version it showed as newest elsewhere (when there was one), `reason` the rule's, and `community` is `true` for a community rule |

A row counts as outdated when `nixStatus` is `outdated`, `upstream.newer`
is `true` (a newer release, for a versioned attribute in its own series),
or master has a newer version. `legacy` (an older version kept beside a
newer one, `keptBeside`) isn't outdated by itself, except for a devel row
behind the newest devel version elsewhere (`refVersion`).

`upstream`:

| Field | Meaning |
|---|---|
| `version` | the newest version the check found (for an unstable version, nixpkgs' version moved to the newest commit's date) |
| `newer` | whether that counts as newer than nixpkgs' (for a branch check, only once `outdatedAfter` says so) |
| `label`, `url` | where it looked: `wesnoth/wesnoth tags`, `www.barebones.com`, ... |
| `repo` | the GitHub repository, for GitHub checks |
| `commit`, `behind`, `outdatedAfter` | branch checks: the newest commit, how many commits since nixpkgs' version, and the limits (`{ "days", "commits" }`) |
| `checkedAt` | when it was last checked (left out: at `checkedAt`) |
| `community` | `true` when the check is a [community rule](community.md) |
| `inferred` | `true` when the check was worked out from nixpkgs' source (the GitHub tags it fetches from), for a package without a rule |
| `rule` | a short fingerprint of the rule that found it: an edited rule runs again at once |
| `page` | page checks: the page's `etag` and `lastModified`, as its server gave them, and the `pattern` it was read with; next time the server is asked to send the page only if it changed, and if it didn't, `version` still holds |

### Master and update PRs

| Field | Meaning |
|---|---|
| `master` | the version Hydra built from master, when it's newer than the channel's. That makes the row outdated, waiting for the channel |
| `openPR` | an open update PR in nixpkgs (below) |
| `masterPR` | an update PR merged into master that the channel doesn't have yet |
| `openPRs`, `openIssues` | how many open nixpkgs PRs and issues have `searchTerm` in their title |
| `countedAt` | when those were last counted (left out: at `checkedAt`): daily, from a listing of all of nixpkgs' open PRs and issues (searched per package instead when that fails: then every 3 days for a package with none open and not outdated) |

`openPR` and `masterPR`: `number`, `title`, `url`, `draft`, `base` (the
branch it targets), and `from` / `to` (the versions in its title,
`name: from -> to`).

### Builds (Hydra)

`builds`: one entry per attribute and platform Hydra builds it on
(x86_64-linux, aarch64-linux, aarch64-darwin); empty for unfree packages.

| Field | Meaning |
|---|---|
| `attr`, `system` | the job |
| `status` | `ok`, `failed`, `dependency` (a dependency failed), `unfinished` (timed out, aborted, ...), `notBuilt` (Hydra has no build), `broken` (nixpkgs marks it broken there), or `unknown` (Hydra couldn't be reached and there's no earlier result) |
| `blockedBy` | for a `dependency` build, which dependency failed, when nixkeeper-hydra's digest has read its page: `[{ "name", "row"? }]`, the row of that package (`row`: `true`; by its name here), or the name Hydra gave it when no job builds it (`source`, a download) |
| `build` | the latest build's id: `https://hydra.nixos.org/build/<id>` |
| `name`, `version` | what that build built (`wesnoth-devel-1.19.28`), and its version |
| `lastSuccess` | when it last built successfully, when the latest build didn't; `null` if it never did |
| `lastSuccessBuild`, `lastSuccessName`, `lastSuccessVersion` | that successful build |
| `checkedAt` | when this job was last read (left out: at `checkedAt`): daily from nixkeeper-hydra's digest; asked of Hydra itself, daily while something's going on, otherwise every 3 days (see [how it works](how-it-works.md)) |

Only `failed` counts as a failure.

### Updates (nixpkgs-update)

| Field | Meaning |
|---|---|
| `update` | the bot's latest attempt (below), or `null` if it never tried |
| `updateFailure` | whether that attempt counts as a failure |
| `queued` | when the bot will try it again, from its queue: `{ "by": "2026-10-12", "candidates": [["4.22.7", "https://github.com/…/releases"], …] }`, the day it's expected (its place in the queue as a share of the queue's cycle) and the versions it would update to that nixpkgs doesn't have, with where it found each (nothing makes the row outdated: the bot's pick can be wrong), and `"script": true` when it also runs the package's updateScript (which decides the version). Missing when it isn't in the queue (the bot sees nothing to update it to) or there's no queue (`sources.queue`) |

`update`:

| Field | Meaning |
|---|---|
| `attr`, `date` | the attribute it tried, and the day |
| `log` | the attempt's log |
| `outcome` | `failed`, `cantUpdate` (a newer version, but no way for the bot to update the package), `prOpened`, `prExists`, `branchExists` (the bot already pushed this update to its branch), `noChange`, `skipped` (the bot passes the package over on purpose), `superseded`, or `other` |
| `from`, `to` | the versions it tried (for an `updateScript` run, read from its diff, or `0` → `1` when it failed before writing one) |
| `was` | what nixpkgs had then: a version, or a name-version (`wesnoth-devel-1.19.24`) |
| `pr` | the PR it opened or found |
| `failedBecause` | for `failed`, why, from the log's first line that says: `unavailable` (broken, insecure or not for x86_64-linux, the package or a dependency), `patch` (nixpkgs' patches or substitutions don't apply), `dependency` (missing or too old), `hash` (one not updated, or one the bot couldn't work out: vendored dependencies, mostly), `source` (the new version's can't be fetched), `updateScript` (the package's own failed), `tests`, `noLog` (the build failed, and nix kept no log), `build` (any other build error), `request` (the bot's own request failed, to GitHub mostly), or `other` |
| `excerpt` | why it failed, couldn't update, was skipped or had nothing to update: for a failure, the line that says what went wrong and the next (the last lines of the log when no line says); else the bot's reasons (for a failed request, its host and answer) |
| `supersededOn` | for `superseded`: `nixos-unstable` or `master` (nixpkgs moved past that version), or `ignored` (a manual rule) |
| `supersededOutcome` | what the attempt was before: `failed` or `cantUpdate` |
| `reason` | the manual rule's reason, for `ignored` |
| `community` | `true` when that rule is a [community rule](community.md) |
| `parser` | the version of the rules the log was read with: the next sync reuses this reading instead of downloading the same log again, unless those rules have changed since |

### Sources that couldn't be refreshed

`notRefreshed`: for each source that failed on the last sync (`builds`,
`update`, `upstream`), `{ "since", "reason" }`: since when it's been failing
and why. That part of the row is then the last known result.
