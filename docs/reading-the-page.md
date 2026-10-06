# Reading the page

Each row is a package; clicking it opens its details (every repository
Repology compares it with, after `nixkeeper` first when an update check found
a version: hover it for where; links to its homepage and nixpkgs source), and
clicking its build or update cell opens that instead. The counts at the top
(tracked, outdated, failed, and flagged vulnerable when any are) filter the
list, as do the list names beside them and a row's platform tags; the filters
stay in the address, so a view can be shared. The search box matches names;
`@handle` instead lists a maintainer's packages (their whole GitHub handle,
as nixpkgs lists it in `meta.maintainers`), and `@none` the packages with no
maintainer. The details panel lists each package's maintainers: clicking one
searches for theirs, so `?q=@yourhandle` is a link to your own. Its teams
(nixpkgs' `meta.teams`), when it has any, are listed too: clicking one shows
only that team's packages, as `?team=` does in the address
(`?team=gaming`, in any case).

Any list can be narrowed further, together with everything else (under the
counts; with every package, under a list's tiles): **without maintainer**,
**not marked broken** (failures nobody has marked yet), **not fixed on
master yet** (leaving out outdated packages whose update is merged and
waits for nixos-unstable), and **older than** a month, 6 months or a year:
how long it's been failing or outdated (the counts' kind, when one is
picked: failing for over 6 months, say). Each count then counts what's
left. In the address: `?refine=unmaintained,notbroken,notonmaster` and
`?age=1m`, `6m` or `1y`, so "failing for 6 months, with no maintainer" is a
link. The dates only go back to when nixkeeper started following a package,
so "older than" finds more as time goes on.

On a page tracking [every package](all-packages.md) (a community
instance), the page starts from an **overview** of nixpkgs, with no list:

- how many packages nixpkgs has, how many are **fully checked** and how many
  are in **generated sets** (pending: only Repology's versions and Hydra's
  builds);
- five cards for the fully checked ones: outdated (fewer than Repology's
  nixpkgs page counts: that includes the generated sets, counts every
  attribute of a package, and takes any newer version it knows of, where
  nixkeeper's own update checks overrule it), build failures (a build of
  its own failing; with how many Hydra builds fail in all, as
  [zh.fail](https://zh.fail/) counts them: every job on every platform, a
  dependency's failure counted for each package it stops), update failures
  (nixpkgs-update's attempts failing: often a sign the update needs doing
  by hand rather than something broken), vulnerable and marked broken,
  each with its trend
  (from the second daily sync on, the last 30 days at most) and its change
  over the last week (since the first sync until there's a week: hover it
  for which). A dashed mark on the trends is a staging-next merge into
  master (mass rebuilds: failing builds jump for days after; its PR is
  linked under the cards), or, in the accent colour, nixkeeper updated or
  counting differently (a change in how it counts can step a count). While
  the digest of nixpkgs-update's attempts is still reading past ones, the
  Update failures card says how many are to go: update failures that were
  there all along keep turning up until then, so it rises without anything
  breaking. Each card opens its list;
- a search box (a package's name, or `@handle`) and a team picker; while
  searching, the matches take the place of what follows, which comes back
  once the search is cleared. Typing `@` and part of a handle suggests the
  maintainers whose handle matches, with their counts (in the overview's
  box, the overview stays while you type: a click or Enter opens theirs); "browse every
  maintainer" (`?view=maintainers`) lists them all by handle, the search
  narrowing them;
- the newest and longest-standing build failures, outdated packages and
  update failures (a switch on each), and "show all" for the whole list;
  and the failing packages **blocking the most** others: a build that
  fails because one of its dependencies did, as zh.fail counts them in all
  of nixpkgs (fix that one, and they all build again);
- what was fixed in the last week: builds that work again, packages
  updated (from and to which version), and nixpkgs-update failures
  cleared, from the first daily sync with this on;
- the generated sets, each with its size and how much of it is marked
  broken or failing (a bar).

At the top, "needs attention" (failing, outdated or flagged vulnerable,
worst first) opens that list from anywhere; "Your packages" (your GitHub
handle) and "Your team" open yours, once given (they're kept in your
browser only, and ✎ changes them). A list says what it is under
"Showing" (✕ goes back to the overview): what needs attention, marked
broken, a maintainer's packages (`?q=@handle`, `@none` for those with
none), a team's (`?team=`), a generated set's (`?set=`), one package alone
(`?pkg=firefox`), or one of the instance's lists (`?list=`, by address
only). Its tiles (outdated, failing, vulnerable, marked broken) count it and
filter it, as the counts at the top do on other pages; the search and order
work within it too, and a search also lists the packages beyond it whose
names match, closest first. "not on Repology" is a package Repology doesn't
know, and "not read" an update attempt the sync didn't read (with every
package, attempts come from a digest of the bot's, which hasn't read that
one yet).

The list shows 200 packages at a time, most in need of attention first;
the page links under it go through the rest (the page is in the address
too, `?page=2`). Changing a filter, the search or the order goes back to the
first page. The browser's find (Ctrl+F) only sees the page shown: the search
box looks through every package.

**Where the data is from**: "checked … ago", at the top, opens when each
source's data is from: the daily sync, the Hydra evaluation its builds are
from, when Repology's versions and nixpkgs-update's attempts were read (and
how many attempts are still to read), the nixpkgs commit. A source the sync
didn't use (too old, or it couldn't be read) says so in yellow: its
packages were then asked about one by one instead.

**The dot** in front of each package (hover it for what it means, or open
the `?` next to "checked" at the top for all of them):

| Dot | Means |
|---|---|
| green | up to date: nixpkgs has the newest version (for a devel package, the newest devel one), or is the only one packaging it, or an [up-to-date rule](community.md#up-to-date-rules-until-something-changes) says Repology gets its version wrong (the details say why) |
| orange | outdated: Repology or nixkeeper's own update check knows a newer version |
| violet | outdated, but the update is already merged on master, waiting for nixos-unstable (usually a few days). Master having a newer version than the channel counts too, even before Repology or an update check knows of it |
| pink | not in nixpkgs unstable (counted as failed) |
| grey | Repology can't compare the version: `untrusted`, `rolling`, `noscheme`, `incorrect` (shown as a badge); or an **older version** nixpkgs keeps on purpose beside a newer one (`tracy_0_11` beside `tracy`, `php82Extensions` beside PHP 8.4's): not outdated while nothing newer is out in its own series, and the details name the newer one |

**The version**: nixpkgs unstable's. For an outdated package, the newest
version is under it, after a `→`, with the start they share faded, so the
part that changes stands out (orange; violet when the update is already on
master):

```
  1.19.24
→ 1.19.28          ("1.19." faded, "28" in colour)
```

Versions are compared by whole parts (split at `.`, `-`, `_`, `+`, `~`), so
`1.19.24 → 1.19.28` colours `28`, and an unstable version only its new date.
When an update is merged into master but a newer release is already out,
master's version gets a line of its own in between, with its `on master`
badge, and the newest under it with its PR:

```
  154.0.8037.57
→ 154.0.8037.92    on master
→ 154.0.8037.97    PR #569374
```

Click the versions to copy the update's title as nixpkgs writes it, for a
commit or a PR: `unciv: 4.22.1 -> 4.22.6` (from master's version when it's
partway there).

How long a package has been outdated shows after its name (`3 d`; violet
when the update is merged and waiting for the channel), and how long it's
been failing, in red, when it fails (its builds since their last success,
its update attempts since the first failed one nixkeeper read). Failing
packages come longest first, as outdated ones do.

**At the right of the versions**: beside nixpkgs' version, the badges
about it (`devel`, `vulnerable`, ...); beside the newest, the update's
(`PR #123`, `on master`, `check failing`):

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
| blocked (gold) | it didn't build because a dependency failed: not its own failure, so not counted as failed; the panel says which dependency (its package, to open), once nixkeeper-hydra has read the build |
| not built by Hydra | unfree, or kept off Hydra by nixpkgs |
| none reported | no failure of its own; an unfinished build shows only in the panel |

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
