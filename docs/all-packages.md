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
| nixpkgs-update | not read for now (about 4,000 packages' logs change a day, more than a sync can read politely): a package keeps the attempt last read, if any, and says it wasn't read (`unread`) |
| GitHub | PR and issue counts and update PRs from the bulk listings only |

Packages of **generated sets** (rPackages, haskellPackages, emacsPackages,
typstPackages, texlivePackages, sbclPackages: their own tooling generates
them from CRAN, Hackage and so on) are **pending**: Repology's versions and
Hydra's builds only, no update attempts or GitHub counts, and left out of
"needs attention" and the counts at the top. More may come set by set.

## The page

It starts from the counts for all of nixpkgs and what needs attention
(failing or outdated), and shows one view at a time: a maintainer's
packages (`?q=@handle`), a team's, a list's, a generated set's, or one
package (`?pkg=`); see [reading the page](reading-the-page.md).

## What it costs

No requests beyond the bulk ones a list-based instance makes. The data is a few hundred MB (about 30 MB gzipped),
written as [views](data.md#every-package) the page starts from instead of
one summary of every package. The sync holds every row at once: a few GB
of memory.
