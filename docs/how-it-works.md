# How it works

The diagram in the [README](../README.md#how-it-works) shows the parts; here
is what each does.

There's no server: nixkeeper is a program that gathers data, and a static
page that shows it.

- **The daily sync** (`nix run .#sync`, run by the "Data: daily sync"
  workflow at 06:00 UTC) works out which packages to track from
  `package-lists/` and the nixos-unstable channel's package index, then asks
  each source about them: Repology for versions, nixkeeper's own update
  checks, Hydra for builds (and nixpkgs for where it marks them broken), the
  nixpkgs-update logs for the bot's latest attempt, and GitHub for open PRs,
  issues and update PRs. It writes everything as JSON to the `data` branch
  ([data.md](data.md)) and rewrites the status issue, commenting when
  something newly needs attention.
- **The hourly checks** ("Data: hourly updates") refresh a few rows of the
  last published data: the update checks marked `frequent` (browsers, for
  their security fixes) and outdated packages' update PRs. They commit only
  when something changed. GitHub runs scheduled workflows on a best-effort
  basis, so "hourly" can stretch to a few hours when Actions is busy; the
  daily sync still covers everything.
- **The page** (`page/`, published to GitHub Pages by a workflow) is plain
  HTML and JavaScript that reads the JSON in your browser.

When a source can't be reached, the row keeps its last known result, marked
as not refreshed, and the status issue says so; the rest of the sync goes
on. nixkeeper asks each source one thing at a time, with a pause between
requests (update checks' pages: one a second per site, taking turns between
sites), and when a source says to slow down (a `Retry-After`), it waits as
long as asked, up to 5 minutes, before trying again. Hydra's builds come
first from [nixkeeper-hydra](https://github.com/iedame/nixkeeper-hydra), a
digest of every job in Hydra's newest evaluation of master that its own
workflow keeps up to date hourly: one download answers most jobs, every day.
The digest is used when it's from Hydra's newest evaluation, or was read in
the last 12 hours; otherwise (or when it can't be downloaded) Hydra is asked
about each job, as it is for the jobs the digest can't answer: missing from
it, not built yet, or failing with no known last success. Asked that way,
Hydra is the slowest source (a request or more per package and platform):
it's asked in the background while the other sources are, and the sync takes
about as long as Hydra rather than all of them in turn; each server still
gets one request at a time. It's also asked less about what's quiet: a job
that built fine, for a package that's up to date with nothing changed or
pending, is asked every 3 days (a third of them each day) instead of daily,
so a new build failure there can show up to 3 days late; anything failing,
outdated, newly changed or with an update PR is asked daily. The builds
panel says when they were last checked. The same goes for update checks that
found nothing newer, unless they're marked `frequent`; and for Repology: a
package that's up to date, not flagged vulnerable and unchanged in nixpkgs
is looked up every 3 days, so its new releases can show up to 3 days late
(most packages are updated by nixpkgs-update, which comes round about every
ten days anyway). Most packages don't need Repology asked at all, though:
their projects come from
[nixkeeper-versions](https://github.com/iedame/nixkeeper-versions), a digest
of every nixpkgs project that its own workflow reads in bulk daily, the way
nixpkgs-update reads Repology (outdated projects every day, the rest every
week). Repology is still asked about a package that isn't in the digest (new
in nixpkgs) or has another version there than the channel's (changed since),
and about every package, as above, when the digest is more than 36 hours old
or can't be read. nixpkgs-update's attempts likewise come from
[nixkeeper-updates](https://github.com/iedame/nixkeeper-updates), a digest
of the bot's latest attempt at every package, its log read with nixkeeper's
own rules, made every 3 hours from the bot's state; a package's logs are
still read when the digest hasn't read its latest attempt yet, or is more
than 12 hours old. GitHub's open PRs and issues aren't searched package by
package: each sync lists all of nixpkgs' open ones (about 120 requests) and
the PRs merged into master since the channel's commit (about 10), and finds
each package's counts and update PRs in their titles, every package daily
(searched per package only when a listing fails). nixkeeper doesn't ask
twice for what can't have changed: a package's Repology project is the one
the last sync found, a package whose bot logs haven't changed since (the log
site's index says when each last changed) isn't listed again, a release page
whose server says it hasn't changed isn't downloaded again, and a log
already read (the bot tries each package about every ten days) is taken from
the previous sync instead of downloaded again.

## How much it tracks

Most of a sync's cost is the same whatever the lists' size: the package
index, the digests of Hydra's builds and Repology's data, and the listings
of nixpkgs' open and merged PRs (about 150 requests and 2 minutes). On top
of that, a package costs about 0.3 requests and half a second on a typical
day (the Hydra jobs the digest can't answer, its update-log folder when it
changed), and about 3 requests and 3 seconds the first time it's synced
(its update-log folder read whole): 1,500 packages take about 12 minutes a
day. A sync starts by saying how long it should take, counting the packages
new to it (on GitHub, in the run's summary too). From 1,500 packages, the list check warns on the page
and in the status issue; above 5,000, the sync refuses to start, so a big
team or a typo can't send thousands of requests by accident. To track more
on purpose, raise the limit in the lists: `maxPackages = 6000;`
(`lists.maxPackages` in the modules). On GitHub Actions, a sync has to
finish within 6 hours, or nothing is published: about 8,000 new packages
at once. Add big lists in stages, since only new packages cost that much;
the sync warns when one may run that long. If most Repology lookups fail,
the sync stops and leaves the published data as it was.

## What gets tracked

`package-lists/default.nix` lists GitHub handles under `maintainers` (every
nixpkgs package they maintain is tracked) and imports further named lists
under `extraPackages` (`extra`, `gaming-team`, ...) of nixpkgs attribute names
(exactly that package, e.g. `haskellPackages.pandoc`) or pnames (every
top-level package with that pname).

Each list is a filter on the page, next to `maintained` for the packages
found through `maintainers`. `?list=gaming-team` in the address is a page of
just that list, to share with the people it's for.

Update checks (`package-lists/update-checks.nix`) look for new releases
Repology doesn't count yet. A package without one of its own (or a community
rule) gets one worked out from nixpkgs: fetched from a GitHub tag, it's
checked against that repository's tags, in the scheme nixpkgs' tag shows
(`v1.2.3`, ...), plain versions only, and is left to Repology when that
check fails; `workedOutChecks = false;` turns these off. The daily sync's
log compares them with Repology ("Worked-out update checks"). Ignore rules
(`package-lists/ignored-updates.nix`) mark failed nixpkgs-update attempts
that don't count, and up-to-date rules (`package-lists/up-to-date.nix`) mark
versions Repology gets wrong. With
`community = { ... }`, the lists also use the [community rules](community.md)
of each kind, which anyone can add to, for the packages they track.

To set the lists up for a dashboard of your own, see
[your own instance](your-own-instance.md); the data each sync writes is
described in [data.md](data.md).
