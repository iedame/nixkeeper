# The data

Everything the page shows comes from plain JSON files, which each sync
rewrites and commits to the `data` branch, under `data/`:

- `index.json`: every tracked package, one row each (below)
- `<project>.json`: each Repology project's raw data, as Repology returns it
  (a list of one entry per repository that packages it: `repo`, `version`,
  `status`, `srcname`, ...); a row's `dataFile` names its file

On GitHub they're at
`https://raw.githubusercontent.com/<owner>/<repo>/data/data/index.json`.

Fields are only present when they have something to say: a field missing
from a row means none (no open update PR, never outdated, ...). Dates are ISO
8601 in UTC (`2026-09-30T06:00:00+00:00`), or a plain day (`2026-09-26`) where
the source only has that. New fields may be added; existing ones change only
with a note in the [changelog](../CHANGELOG.md).

## `index.json`

```json
{ "checkedAt": "2026-09-30T06:00:00+00:00", "version": "0.9.0", "packages": [ ... ] }
```

`version` is the nixkeeper that ran the last full sync (the page shows it
at the bottom). `checkedAt` is when the last full sync ran (the hourly
checks update single rows without changing it). `packages` are the rows,
sorted by name.
`listProblems`, only when there are any, lists mistakes the sync found in the
package lists, as sentences: a maintainer handle no package lists, an extra
package nixpkgs doesn't have, an update check or ignore rule for a package
that isn't tracked, or 500 packages or more (the cost of a sync). The page shows them above the table. `page`, only when
the lists set it, holds the page's settings: `{ "theme": "catppuccin" }` is
its default palette.

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
| `source` | where nixpkgs defines it, on GitHub at the channel's commit and line |
| `unfree` | `true` when every attribute is unfree (Hydra doesn't build those) |

### Versions (Repology, and nixkeeper's own checks)

| Field | Meaning |
|---|---|
| `nixVersion` | the version in nixos-unstable |
| `nixStatus` | Repology's status for it: `newest`, `outdated`, `devel`, `unique`, `legacy`, `untrusted`, `rolling`, `noscheme`, `incorrect`, ..., or `missing` when nixpkgs doesn't have it |
| `refVersion` | the newest version seen elsewhere (for a devel row, the newest devel one), or what nixkeeper's update check found, or what master has (`master`), whichever is newest |
| `refFromMaster` | `true` when `refVersion` is master's: newer than anything Repology or an update check knows of |
| `repoCount` | how many other repositories Repology compares it with |
| `devel` | a development variant of a split project (`wesnoth-devel`), or a version Repology calls devel |
| `nixVulnerable` | Repology flags `nixVersion` as vulnerable (its CVEs: `https://repology.org/project/<project>/cves`) |
| `outdatedSince` | when nixkeeper first saw it outdated; gone once it's caught up |
| `staleSince` | Repology couldn't be reached for it: the version data is from this time |
| `upstream` | nixkeeper's own update check, when it has one (below) |

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
| `checkedAt` | when it was last checked |
| `community` | `true` when the check is a [community rule](community.md) |

### Master and update PRs

| Field | Meaning |
|---|---|
| `master` | the version Hydra built from master, when it's newer than the channel's. That makes the row outdated, waiting for the channel |
| `openPR` | an open update PR in nixpkgs (below) |
| `masterPR` | an update PR merged into master that the channel doesn't have yet |
| `openPRs`, `openIssues` | how many open nixpkgs PRs and issues have `searchTerm` in their title |

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
