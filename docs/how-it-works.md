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
requests, and when a source says to slow down (a `Retry-After`), it waits
as long as asked, up to 5 minutes, before trying again. It doesn't ask
twice for what can't have changed: the bot's log of an attempt it has
already read (the bot tries each package about every ten days) is taken from
the previous sync instead of downloaded again.

## How much it tracks

Every tracked package costs each sync about 8 requests to public services
(Repology, Hydra, the nixpkgs-update logs, GitHub) and about 7 seconds. A
sync starts by saying how long it should take (on GitHub, in the run's
summary too). From 500 packages, the list check warns on the page and in the
status issue; above 2,000, the sync refuses to start, so a big team or a
typo can't send thousands of requests by accident. To track more on
purpose, raise the limit in the lists: `maxPackages = 3000;`
(`lists.maxPackages` in the modules). On GitHub Actions, keep a sync under
its 6-hour limit: about 3,000 packages. If most Repology lookups fail, the sync stops and leaves the published
data as it was.

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
Repology doesn't count yet, ignore rules (`package-lists/ignored-updates.nix`)
mark failed nixpkgs-update attempts that don't count, and up-to-date rules
(`package-lists/up-to-date.nix`) mark versions Repology gets wrong. With
`community = { ... }`, the lists also use the [community rules](community.md)
of each kind, which anyone can add to, for the packages they track.

To set the lists up for a dashboard of your own, see
[your own instance](your-own-instance.md); the data each sync writes is
described in [data.md](data.md).
