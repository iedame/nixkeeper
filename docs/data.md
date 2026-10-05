# The data

Everything the page shows comes from plain JSON files, which each sync
rewrites and commits to the `data` branch, under `data/`. That branch is
always `main` plus one commit with the latest data: each run replaces it, so
it keeps no history.

- `index.json`: the sync's details (when, which version, list problems),
  the counts of rows and shards, and, for now, every row (`packages`)
- `summary.json`: a short entry per row, with what the page's list needs
  (below)
- `rows/<n>.json`: the rows in full, with their Repology entries, in shards
  (below)
- `<project>.json`: each Repology project's packages, as Repology lists
  them: one entry per repository and package, with only what nixkeeper reads
  (`repo`, `srcname`, `version`, `status`, and `vulnerable` when flagged),
  each once; a row's `dataFile` names its file. For now: the shards hold
  the same entries

`packages` in `index.json` and the `<project>.json` files are the data's
first format, which pages from 0.11.0 and before read; format 2 (`summary.json`
and the shards) is what lets the page load only what it shows, and what it
reads since 0.12.0 (it still reads the first format, for data from before). Both are
written for now; the first format will be dropped in a later release, with a
note in the changelog.

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
{ "format": 2, "checkedAt": "2026-09-30T06:00:00+00:00", "version": "0.12.0",
  "packageCount": 241, "shardCount": 1, "packages": [ ... ] }
```

`format` is the data's format (2; missing in data from before). `version`
is the nixkeeper that ran the last full sync (the page shows it at the
bottom). `checkedAt` is when the last full sync ran (the hourly checks update
single rows without changing it). `packageCount` is how many rows there are,
`shardCount` how many shards hold them. `packages` are the rows, sorted by
name (the first format, for now).

`listProblems`, only when there are any, lists mistakes the sync found in the
package lists, as sentences: a maintainer handle no package lists, an extra
package nixpkgs doesn't have, an update check, ignore or up-to-date rule for
a package that isn't tracked, or 1,500 packages or more (the cost of a sync).
The page shows them above the table. `page`, only when the lists set it,
holds the page's settings: `{ "theme": "catppuccin" }` is
its default palette.

## `summary.json`

```json
{ "packages": [ ... ] }
```

One entry per row, sorted by name: the row (below) without what only its
details show (`dataFile`, `homepage`, `repoCount`, `repologyCheckedAt`,
`source`), its builds with only `status` and `system`, its `update` with only
`outcome` (still `null` when the bot never tried, missing when it isn't in
nixpkgs), and its `upstream` with only `version`, `newer`, `community` and
`inferred`.

## `rows/<n>.json`

```json
{ "packages": [ ... ] }
```

The rows in full, sorted by name, each with its Repology project's entries
in `repology` (as in `<project>.json`; missing when there are none). Rows
are spread over `shardCount` shards (a power of two, about 500 rows each) by
a hash of their name: a row is in shard `crc32(name) % shardCount` (CRC-32
of the name's UTF-8 bytes, as zlib computes it), so a new package changes
only its own shard.

## Every package

With [every package](all-packages.md) tracked, `index.json` says
`"allPackages": true` and there's no `summary.json` (every package's entry
would be too much to load), no `packages` in `index.json` and no
`<project>.json` files (the shards hold the entries; for packages not on the
lists, nixpkgs' own and those of the 8 newest other repositories). Instead:

- `counts` in `index.json`: `tracked`, `outdated`, `failed`, `vulnerable`,
  `updateFailures`, `waiting` (outdated, the update merged on master) of the
  rows not pending, and `pending`;
- `views` in `index.json`: how many rows `attention` has, and the `teams`,
  `lists` and `sets` with their counts (`{ "Gaming": 12, ... }`);
- `views/`, each `{ "packages": [ ... ] }` of summary entries, sorted by
  name: `attention.json` (failing or outdated, not pending),
  `maintainer/<handle>.json` (the handle in lowercase; `none.json`: no
  maintainer, not pending), `team/<slug>.json` and `list/<slug>.json` (the
  name in lowercase, each run of other characters than letters and digits
  a `-`: `Security review` is `security-review`), `set/<name>.json` (a
  generated set's pending rows);
- `names.json`: `{ "names": [ [name, status], ... ] }` for every row, with
  its set as a third element when it's pending. `status` is a letter as the
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
| `project`, `dataFile` | its Repology project, and that project's file in `data/` |
| `platforms` | `{ "linux": bool, "darwin": bool }` from `meta.platforms`; `null` when nixpkgs doesn't restrict them |
| `homepage` | `meta.homepage` |
| `maintainers` | the GitHub handles in `meta.maintainers`, of all its attributes; `[]` when nixpkgs lists none (with a handle), missing when nixpkgs doesn't have it |
| `teams` | the nixpkgs teams in `meta.teams` (`maintainers/team-list.nix`), of all its attributes, by their short name (`Gaming`, `Qt-KDE`); missing when it has none |
| `pending`, `set` | with every package: `true` and its set for a row of a generated set (`haskellPackages`, ...) that no list has: only Repology's versions and Hydra's builds ([every package](all-packages.md)) |
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
| `devel` | a development variant of a split project (`wesnoth-devel`), or a version Repology calls devel |
| `nixVulnerable` | Repology flags `nixVersion` as vulnerable (its CVEs: `https://repology.org/project/<project>/cves`) |
| `outdatedSince` | when nixkeeper first saw it outdated; gone once it's caught up |
| `staleSince` | Repology couldn't be reached for it: the version data is from this time |
| `repologyCheckedAt` | when its Repology data was read: the day nixkeeper-versions' digest read it (daily for outdated projects, weekly for the rest), or when Repology was asked directly (daily while it's outdated, flagged vulnerable, changed in nixpkgs or new, otherwise every 3 days) |
| `upstream` | nixkeeper's own update check, when it has one (below): a rule of yours or the community's, or one worked out from nixpkgs |
| `upToDate` | an [up-to-date rule](community.md#up-to-date-rules-until-something-changes) applies: Repology gets `nixVersion` wrong, so `nixStatus` is `newest` and there's no `refVersion`. `status` is what Repology said, `newest` the version it showed as newest elsewhere (when there was one), `reason` the rule's, and `community` is `true` for a community rule |

A row counts as outdated when `nixStatus` is `outdated` or `legacy`, or
`upstream.newer` is `true`.

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

`update`:

| Field | Meaning |
|---|---|
| `attr`, `date` | the attribute it tried, and the day |
| `log` | the attempt's log |
| `outcome` | `failed`, `cantUpdate` (a newer version, but no way for the bot to update the package), `prOpened`, `prExists`, `noChange`, `superseded`, or `other` |
| `from`, `to` | the versions it tried (for an `updateScript` run, read from its diff, or `0` → `1` when it failed before writing one) |
| `was` | what nixpkgs had then: a version, or a name-version (`wesnoth-devel-1.19.24`) |
| `pr` | the PR it opened or found |
| `excerpt` | why it failed or couldn't update: the last lines of the log, or the bot's reasons |
| `supersededOn` | for `superseded`: `nixos-unstable` or `master` (nixpkgs moved past that version), or `ignored` (a manual rule) |
| `supersededOutcome` | what the attempt was before: `failed` or `cantUpdate` |
| `reason` | the manual rule's reason, for `ignored` |
| `community` | `true` when that rule is a [community rule](community.md) |
| `parser` | the version of the rules the log was read with: the next sync reuses this reading instead of downloading the same log again, unless those rules have changed since |

### Sources that couldn't be refreshed

`notRefreshed`: for each source that failed on the last sync (`builds`,
`update`, `upstream`), `{ "since", "reason" }`: since when it's been failing
and why. That part of the row is then the last known result.
