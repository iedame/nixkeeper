# Every package

nixkeeper normally tracks the packages your lists name. It can also track
**every package in nixpkgs**, for a community instance anyone can look up
their packages on (`?q=@handle`, `?team=`): about 150,000 attributes, in
about 120,000 rows (the attributes of one Repology project share a row,
like python313Packages.requests and python314Packages.requests).

Turn it on for one instance only:

- on GitHub: the repository variable `NIXKEEPER_ALL_PACKAGES` set to `1`
  (Settings → Secrets and variables → Actions → Variables). A variable,
  not a setting in `package-lists/`: forks copy those files, and a fork
  that only changes `maintainers` shouldn't start tracking all of nixpkgs;
- with the NixOS or nix-darwin module: `services.nixkeeper.allPackages = true`;
- with the command: `nixkeeper sync --all-packages`, or
  `NIXKEEPER_ALL_PACKAGES=1`.

## What each package gets

Your lists still count: their packages are read as always (every source,
looked up one by one when the bulk sources can't answer), and only they are
in the status issue. The rest of nixpkgs is read in bulk only, with nothing
asked package by package:

| Source | Packages not on the lists |
|---|---|
| Repology | from [nixkeeper-versions](https://github.com/iedame/nixkeeper-versions)' digest, as it has them; a package it doesn't have is "unlisted" (nixpkgs' version, nothing to compare it with) |
| Hydra | from [nixkeeper-hydra](https://github.com/iedame/nixkeeper-hydra)'s digest; a queued job keeps its last result |
| `meta.broken` | the package index's (x86_64-linux), not evaluated per platform |
| Update checks | your own and the community's rules; none worked out from nixpkgs |
| nixpkgs-update | from [nixkeeper-updates](https://github.com/iedame/nixkeeper-updates)' digest, its last read attempt; a package whose attempts it hasn't read yet says so (`unread`). Without the digest, not read (about 4,000 packages' logs change a day, more than a sync can read politely) |
| GitHub | PR and issue counts and update PRs from the bulk listings only |

Packages of **generated sets** (rPackages, haskellPackages, emacsPackages,
typstPackages, texlivePackages, sbclPackages: their own tooling generates
them from CRAN, Hackage and so on) are **pending**: Repology's versions and
Hydra's builds only, no update attempts or GitHub counts, and left out of
"needs attention" and the counts at the top. More may come set by set.

## The page

It starts from an overview of all of nixpkgs: the fully checked packages'
outdated, failing, vulnerable and broken counts with their trends (from
`history.json`, a point a daily sync), a search (and every maintainer, by
handle), the newest and longest-standing failures, what was fixed in the
last week, and the generated sets. Each opens a list: what needs
attention, a maintainer's packages (`?q=@handle`), a team's, a generated
set's, or one package (`?pkg=`); visitors can keep their own handle and
team, in their browser. See [reading the page](reading-the-page.md).

## Starting the runs on time

GitHub runs scheduled workflows on a best-effort basis and skips runs when
it's busy: some days the hourly digests ran a handful of times. Any machine
that stays on can start them on time instead, through GitHub's API:
`nix run .#start-runs`, hourly a little after the hour, starts each
digest's run when it's due and the daily sync at 06 UTC
([scripts/start-runs.sh](../scripts/start-runs.sh); `-- --dry-run` shows
which, without starting anything). The workflows keep their own schedules
as a fallback: a run started twice finds nothing new, or stops at once.

It needs a [fine-grained token](https://github.com/settings/personal-access-tokens/new)
for the four repositories (nixkeeper and the three digests) with only
**Actions: read and write**: it can start and cancel runs, nothing else.
On a Mac, keep it in the Keychain (this asks for it):

```bash
security add-generic-password -a "$USER" -s nixkeeper-start-runs -w
```

(elsewhere, in a file named by `NIXKEEPER_START_TOKEN_FILE`), and run it
from nix-darwin, with nixkeeper as a flake input:

```nix
launchd.user.agents.nixkeeper-start-runs.serviceConfig = {
  ProgramArguments = [
    (lib.getExe inputs.nixkeeper.packages.${pkgs.stdenv.hostPlatform.system}.start-runs)
  ];
  StartCalendarInterval = [ { Minute = 15; } ]; # hourly, at :15
  StandardOutPath = "/Users/you/Library/Logs/nixkeeper-start-runs.log";
  StandardErrorPath = "/Users/you/Library/Logs/nixkeeper-start-runs.log";
};
```

A user agent runs while that user is logged in (the Keychain is theirs).
launchd's minute is the Mac's local time: in a time zone with a
half-hour offset, choose the minute that's :15 in UTC (45 for UTC+5:30).

## What it costs

No requests beyond the bulk ones a list-based instance makes. The data is a few hundred MB (about 30 MB gzipped),
written as [views](data.md#every-package) the page starts from instead of
one summary of every package. The sync holds every row at once: a few GB
of memory.
