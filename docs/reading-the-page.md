# Reading the page

Each row is a package; clicking it opens its details (every repository
Repology compares it with, after `nixkeeper` first when an update check found
a version: hover it for where; links to its homepage and nixpkgs source), and
clicking its build or update cell opens that instead; one package is open
at a time, so opening another closes it. The counts at the top
(tracked, outdated, failed, and flagged vulnerable or blocked when any are)
filter the list, as do the list names beside them and a row's platform tags
(Linux, Darwin, or "Linux x86_64" for a package on only one Linux system); the filters
stay in the address, so a view can be shared. The search box matches names;
`@handle` instead lists a maintainer's packages (their whole GitHub handle,
as nixpkgs lists it in `meta.maintainers`), and `@none` the packages with no
maintainer. The details panel lists each package's maintainers: clicking one
searches for theirs, and the address becomes `?maintainer=yourhandle`, a
link to your own (`?q=@yourhandle`, as it was first written, still opens
it and becomes that). Its teams
(nixpkgs' `meta.teams`), when it has any, are listed too: clicking one shows
only that team's packages, as `?team=` does in the address
(`?team=gaming`, in any case). With a `-`, `?team=` leaves a team's
packages out instead, on any list (`?maintainer=l0b0&team=-Geospatial`; several:
`team=-Geospatial,-Gaming`, each a chip to undo it); `?team=none` keeps
only what isn't through a team: on a maintainer's page, the packages that
list them themselves (its **Not via a team** button), leaving out those
they maintain only as a member of the package's team (nixpkgs adds a
team's members to each of its packages' maintainers); elsewhere, packages
without a team. `?maintainer=` takes a `-` the same way: `-iedame` leaves
out the packages iedame maintains (directly or through a team), on any
list (`?team=Gaming&maintainer=-iedame`, or beside a maintainer's own page:
`?maintainer=l0b0,-iedame`), each a "not @iedame" chip to undo it.

Any list can be narrowed further, together with everything else (under the
counts; with every package, under a list's tiles): **without maintainer**,
**not marked broken** (failures nobody has marked yet), **not fixed on
master yet** (leaving out outdated packages whose update is merged and
waits for nixos-unstable), **bot won't update it** (outdated packages
nixpkgs-update won't update by itself, so it takes someone: it can't,
skips them on purpose, or has never tried them and they aren't in its
queue; none with an update PR open or merged), on a maintainer's page
**not via a team** (`?team=none`, above), **failed because**
(update failures for one reason, as nixpkgs-update's log says: build,
updateScript, source, dependency, patch, unavailable, tests, hash,
request, "build, no log", bot (the bot's own machine failed, not the
package: when that was in the last 3 days, its details link
nixpkgs-update's issues, to tell them; older, it was a past outage the
bot's next round clears), or
other when none was recognised; each with how
many there are in the list; `?because=patch`), **older than** a month, 6 months, a year, 2 or 3 years:
how long it's been failing or outdated (the counts' kind, when one is
picked: failing for over 6 months, say), or **never built** (a failing
build that never succeeded on Hydra, which has no date; with **on**, only
there: when it's all that fails, the list shows "n/a" instead of how
long, and the build column "never: darwin", say), and **on** Linux, Linux x86_64,
Linux aarch64 or Darwin (macOS, as nixpkgs calls it): the packages
available there, and only their builds there (build failures on
aarch64-linux, say; as clicking a row's platform tag does). Each count then
counts what's left. In the address:
`?refine=unmaintained,notbroken,notonmaster,nobot`, `?age=1m`, `6m`,
`1y`, `2y`, `3y` or `never`, and `?platform=linux`, `x86_64-linux`, `aarch64-linux` or `darwin`
(`macos` still works), so "failing for
6 months, with no maintainer" is a link. A build failure's date is
Hydra's last success; the others only go back to when nixkeeper started
following a package, so "older than" finds more of them as time goes on.

On a page tracking [every package](all-packages.md) (a community
instance), the page starts from an **overview** of nixpkgs, with no list:

- how many packages nixpkgs has, how many are **fully checked** and how many
  are in **sets updated in bulk** (R, Haskell, Emacs, TeX Live, Typst,
  SBCL: kept current by their own tooling, the CRAN import or hackage2nix,
  say, not one PR per package; counted per set, not in the cards);
- five cards for the fully checked ones: outdated (fewer than Repology's
  nixpkgs page counts: that includes the sets updated in bulk, counts every
  attribute of a package, and takes any newer version it knows of, where
  nixkeeper's own update checks overrule it), build failures (a build of
  its own failing; with how many Hydra builds fail in all, as
  [zh.fail](https://zh.fail/) counts them: every job on every platform, a
  dependency's failure counted for each package it stops; and how many
  fail on Linux and on Darwin, each Hydra system on hover), update failures
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
  of nixpkgs (fix that one, and they all build again), and "show all" for
  every package blocked (`?view=blocked`);
- what was fixed in the last week: builds that work again, packages
  updated (from and to which version), and nixpkgs-update failures
  cleared, from the first daily sync with this on;
- the sets updated in bulk, each with its size, what updates it, how
  many are outdated (for Haskell, how many of those are already updated on
  haskell-updates, waiting for its merge), and how much of it is marked
  broken or failing (a bar).

At the top, "needs attention" (failing, outdated or flagged vulnerable,
worst first) opens that list from anywhere; "Your packages" (your GitHub
handle) and "Your team" open yours, once given (they're kept in your
browser only, and ✎ changes them). A list says what it is under
"Showing" (✕ goes back to the overview): what needs attention, marked
broken, blocked by a dependency, fixes to backport (`?view=backport`: a
CVE fixed on nixpkgs master but still affected on the newest release
branch, its own card on the overview; the details say which), a maintainer's packages (`?maintainer=handle`, `none` for those with
none), a team's (`?team=`), a set's (`?set=`), one package alone
(`?pkg=firefox`), or one of the instance's lists (`?list=`, by address
only). Its tiles (outdated, failing, vulnerable, marked broken, blocked) count it and
filter it, as the counts at the top do on other pages; the search and order
work within it too, and a search also lists the packages beyond it whose
names match, closest first. "not on Repology" is a package Repology doesn't
know, and "not read" an update attempt the sync didn't read (with every
package, attempts come from a digest of the bot's, which hasn't read that
one yet).

The list shows 200 packages at a time, most in need of attention first;
the page links under it go through the rest (the page is in the address
too, `?page=2`). "Per page" beside them shows 50, 100, 200, 500 or 1,000 at a time
instead (`?per=500` in the address, kept when moving between views; the
maintainers' list too), staying on the page that holds the first package you
were looking at. Changing a filter, the search or the order goes back to the
first page. The browser's find (Ctrl+F) only sees the page shown: the search
box looks through every package.

**Where the data is from**: "checked … ago", at the top, opens when each
source's data is from: the daily sync, the nixpkgs commit, then each of
nixkeeper's digests with what the sync read from it (nixkeeper-hydra: the
Hydra evaluations of master and haskell-updates; nixkeeper-versions:
Repology and the other version sources, when each was read;
nixkeeper-updates: nixpkgs-update's attempts, with how many are still to
read, and its queue; nixkeeper-vulnerabilities: the NixOS security tracker
and OSV). A source the sync
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
| `insecure` | nixpkgs itself marks it insecure (`meta.knownVulnerabilities`): it won't build unless allowed; the details give nixpkgs' reasons, their CVEs linked |
| `vulnerable` | vulnerable, says one or more of: the NixOS security tracker (a CVE affecting the package), OSV (an advisory listing its version), Repology; hovering says who, and how many CVEs. Red for critical or high severity, orange for medium, grey for low; the vulnerable list goes worst first. The details list each CVE: its severity, the verdict, the tracker's issue and its nixpkgs issue, and the release branches still affected (a fix to backport); the ones not counted (fixed, unconfirmed, dismissed) folded below |
| `untrusted`, `rolling`, ... | Repology's status for a version it can't compare |
| `not refreshed` | Repology couldn't be reached on the last sync: older data |
| `check failing` | nixkeeper's own update check for it isn't working: fix it in `package-lists/update-checks.nix` |

**Build failures** (Hydra, which builds nixpkgs master). The cell opens the
builds panel: how it stands ("Failing on 2 of 3", "Blocked on 1 of 3",
"Building on all 3"), then a row per system with its status, when it last
built, and its log, Hydra job, build or source to open:

| Shows | Means |
|---|---|
| failure reported (pink) | its latest build failed on a platform: the panel links the log and says when it last built, and at which version |
| marked broken (gold) | nixpkgs marks it broken on a platform (known, so not counted as failed) |
| blocked (gold) | it didn't build because a dependency failed: not its own failure, so not counted as failed (the "blocked" count and tile, `?filter=blocked`, list them); the panel says which dependency (its package, to open), once nixkeeper-hydra has read the build |
| not built by Hydra | unfree, or kept off Hydra by nixpkgs |
| none reported | no failure of its own; an unfinished build shows only in the panel |

**Update failures** (the nixpkgs-update bot, r-ryantm; its latest attempt).
The cell opens the update panel: the outcome ("Failed: patch", "PR opened",
"Can't update"...), when it was attempted and from which version to which,
why, the log's last lines, the next attempt from the bot's queue (when, and
what it would update to), and the log and every attempt to open:

| Shows | Means |
|---|---|
| failed: … (pink) | the bot's update failed, and why, from its log: `tests`, `build`, `dependency` (one missing or too old), `patch` (nixpkgs' patches no longer apply), `source` (couldn't be fetched), `hash` (one the bot couldn't work out), `updateScript` (the package's own failed), `unavailable` (broken, insecure or not for x86_64-linux), `request` (the bot's own request failed, not the package). The panel says it in full, with the log's line that says so. `failure reported` when the log doesn't say |
| can't update (gold) | a newer version exists, but none of the bot's ways of updating apply to this package: update it by hand, or give it an updateScript |
| skipped | the bot passes this package over on purpose (the package opts out, GNOME's release cycle, too many rebuilds, ...: the panel says which): while it does, updates are done by hand |
| superseded | the attempt no longer matters: nixpkgs has moved past that version (in the channel, or merged on master), or a manual rule ignores it (`package-lists/ignored-updates.nix`) |
| not attempted | the bot has never tried this package |
| … · a robot's head | joined to any of these: nixpkgs-update will try it, from its queue (screen readers say "queued"). Green when to the newest version and its last attempt didn't fail, so its PR should follow; amber when it will try but it's unsure: its last attempt didn't work, it would update to another version, or only the package's updateScript runs, which decides the version (for outdated packages). Hover it for which; it opens the update panel too, which says when. Not shown while an update PR is open or merged |
| none reported | the bot opened a PR, found one open, had already pushed the update to its branch, had nothing to update (nothing newer by Nix's version order, say), or finished without a recognisable result (the panel says which) |

The update panel also says when the bot will try the package again, from
[its queue](https://nixpkgs-update-logs.nixos.org/~supervisor/queue.html),
which goes round every 10 days or so, and what it would update it to: a
version it found on GitHub or Repology that nixpkgs doesn't have yet. That
doesn't make the package outdated here (the bot's pick can be wrong). A
package not in the queue has nothing the bot could update it to right now.

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
