# Reading the page

Each row is a package; clicking it opens its details (every repository
Repology compares it with, links to its homepage and nixpkgs source), and
clicking its build or update cell opens that instead. The counts at the top
(tracked, outdated, failed, and flagged vulnerable when any are) filter the
list, as do the list names under them and a row's platform tags; the filters
stay in the address, so a view can be shared.

**The dot** in front of each package:

| Dot | Means |
|---|---|
| green | up to date: nixpkgs has the newest version (for a devel package, the newest devel one), or is the only one packaging it |
| orange | outdated: Repology or nixkeeper's own update check knows a newer version |
| violet | outdated, but the update is already merged on master, waiting for nixos-unstable (usually a few days). Master having a newer version than the channel counts too, even before Repology or an update check knows of it |
| pink | not in nixpkgs unstable (counted as failed) |
| grey | Repology can't compare the version: `untrusted`, `rolling`, `noscheme`, `incorrect` (shown as a badge) |

**The version**: nixpkgs unstable's, then for an outdated package `→` the
newer one and how long it's been outdated (`· 3d`). For an unstable version,
the target shows just the new date.

**Badges** after the version:

| Badge | Means |
|---|---|
| `PR #123` (green) | an open update PR in nixpkgs; grey while it's a draft |
| `on master` (violet) | the update is merged into master; links to its PR |
| `devel` | a development release, compared against other devel versions |
| `vulnerable` | Repology flags this version; the details link its known CVEs |
| `untrusted`, `rolling`, ... | Repology's status for a version it can't compare |
| `not refreshed` | Repology couldn't be reached on the last sync: older data |
| `check failing` | nixkeeper's own update check for it isn't working: fix it in `package-lists/update-checks.nix` |

**Build failures** (Hydra, which builds nixpkgs master):

| Shows | Means |
|---|---|
| failure reported (pink) | its latest build failed on a platform: the panel links the log and says when it last built, and at which version |
| marked broken (gold) | nixpkgs marks it broken on a platform (known, so not counted as failed) |
| not built by Hydra | unfree, or kept off Hydra by nixpkgs |
| none reported | no failure of its own; a failed dependency or an unfinished build shows only in the panel |

**Update failures** (the nixpkgs-update bot, r-ryantm; its latest attempt):

| Shows | Means |
|---|---|
| failure reported (pink) | the bot's update failed: the panel shows the end of its log |
| can't update (gold) | a newer version exists, but none of the bot's ways of updating apply to this package: update it by hand, or give it an updateScript |
| superseded | the attempt no longer matters: nixpkgs has moved past that version (in the channel, or merged on master), or a manual rule ignores it (`package-lists/ignored-updates.nix`) |
| not attempted | the bot has never tried this package |
| none reported | the bot opened a PR, found one open, had nothing to update, or finished without a recognisable result (the panel says which) |

A `not refreshed` tag on a build or update cell means Hydra or the update
logs couldn't be reached on the last sync, so it shows the last known result.
The time at the top right is the last sync; it turns pink when that was over
two days ago.

**The tab's icon** shows what needs attention, so a pinned tab tells you at a
glance: each of the mark's three chevrons lights up for its own signal, the
top right orange for a new release (not counting updates already on master),
the left pink for a failure, the bottom pink for a vulnerability. With none,
the top right is green: all good. It follows the list filter, like the counts.

**The Theme menu** (top right) picks the page's colours, Classic or
[Catppuccin](https://catppuccin.com) (Latte when light, Mocha when dark), and
light, dark, or Auto (your system's setting). Your choice is kept in your
browser (its local storage, nothing is sent anywhere) and wins over the
page's default, which its owner sets with `page.theme` in the package lists.
The colours keep their meanings in either palette.
