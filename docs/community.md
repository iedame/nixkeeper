# Community rules

Some of what nixkeeper needs to know about a package is the same for
everyone who tracks it, and worth writing once. [`community/`](../community)
holds rules anyone can add to by pull request, for any nixpkgs package, in
the same format as your own lists:

- **Update checks** ([`community/update-checks.nix`](../community/update-checks.nix)):
  where to look for a package's new releases before Repology counts them (a
  project's tags, the branch an unstable version follows, a release page),
  or which package it's updated together with (`follows`).
- **Ignore rules** ([`community/ignored-updates.nix`](../community/ignored-updates.nix)):
  failed nixpkgs-update attempts that shouldn't count as the bot's failure,
  such as a version upstream never really released.

## Using them

Opt in to each, in your package lists:

```nix
community = {
  updateChecks = true;
  ignoredUpdates = true;
};
```

That's `package-lists/default.nix` for a dashboard of your own (and the
lists `nixkeeper init` writes), or `lists.community` in the
[NixOS](nixos.md) or [nix-darwin](darwin.md) module. Both are off unless
you turn them on, and each works without the other: an ignore rule can hide
a failure, so you might want shared update checks but not shared ignores.

Then each sync:

- uses the community's rules **only for the packages you track**: the rest
  are never used, and an update check for them is never fetched;
- lets **your own rules win**: your update check for a package replaces the
  community's, and your ignore rule for a version replaces its reason;
- says on the page when a result comes from a community rule ("a community
  update check found …", "a version ignored by a community rule").

The rules come with nixkeeper itself, so they're pinned like the rest of it:
new ones arrive when you update nixkeeper (or move to a new
[version](command.md#pinning-a-version)), never in between. They're read
with Nix at each sync.

## Update checks: the limits

Community update checks run on the machine of everyone who opts in, so
they're held to limits your own aren't. One beyond them is refused, never
fetched, and shows as "check failing" on its row, with why:

- **Web pages**: `https://` only, to a public host by name. No IP addresses,
  no `localhost` or local-network names, no ports or credentials in the URL.
  The host has to resolve to public internet addresses only, and so does
  every redirect. A page is read up to 2 MB.
- **Patterns** (`tags`, `pattern`): at most 200 characters, with no repeated
  repeats like `(a+)+` and no back-references, which can take a very long
  time to match.
- **Fields**: only the ones the format has (`github`, `tags`, `branch`,
  `outdatedAfter`, `url`, `pattern`, `frequent`, `follows`); GitHub
  repositories as `owner/repo`.

## Packages updated together

Some packages are always updated with another, to the same version, by the
same PRs: msedgedriver with microsoft-edge, a browser's driver with the
browser. Their PR titles name only the main package, so a search for the
other finds nothing. A `follows` rule says so:

```nix
msedgedriver = { follows = "microsoft-edge"; };
```

The package then counts the other's newest version and update PRs (merged
and open) as its own, in the daily sync and the hourly checks; its builds,
bot attempts and vulnerabilities stay its own. It applies only when you
track both. It fetches nothing, takes no other fields, and can't follow a
package that follows another. The same rule works in your own update
checks.

Your own update checks keep their freedom: they're yours, so a page on your
own network is fine there. Ignore rules fetch nothing, so they need no
limits.

## Ignore rules: short-lived by design

An ignore rule only matters while the bot's latest attempt for that package
is a failure at that version. Once the bot tries another version, the rule
does nothing, and the weekly run lists it as one that can go. They're also
not the fix at the source: to stop the bot trying a version again, that's
Repology's ignore rules or nixpkgs-update's skiplist. A community ignore rule
only stops the failure the bot already made from showing for everyone.

## Adding a rule

1. **Add it** to [`community/update-checks.nix`](../community/update-checks.nix)
   or [`community/ignored-updates.nix`](../community/ignored-updates.nix), in
   the same format as your own (each file's header shows it), keyed by the
   package's nixpkgs attribute. A good update check follows what nixpkgs
   packages (the stable series it tracks, the page its source comes from);
   a good ignore rule says why the version doesn't count. Either way, say so
   in a comment.
2. **Try it**, from your checkout:

   ```bash
   nix run .#community-check -- <attribute>
   ```

   It runs the package's update check for real against nixpkgs' current
   version and says what it found, and checks its ignore rules against the
   bot's latest attempt. GitHub update checks need a token (`GITHUB_TOKEN`,
   or a `gh` login).
3. **Open a pull request.** CI checks the files (`nix flake check`): every
   rule well formed, for a package in nixpkgs, update checks within the
   limits above with valid patterns. The "Community: update checks still
   work" workflow tries the rules your pull request adds or changes for real:
   it fails if an update check finds nothing, or an ignore rule doesn't match
   the bot's latest failed attempt (it would do nothing).

Rather describe an update check than write it? Use the
["Propose a community update check"](https://github.com/iedame/nixkeeper/issues/new?template=community-check.yml)
issue form.

## Keeping them working

The same workflow runs every rule weekly and keeps the **"Community rules
status"** issue up to date: which update checks are broken (a moved page, a
renamed repository), why, and since when, with a comment when one breaks or
works again; and which ignore rules can go. Neither fails the workflow; the
issue is where they show. A broken update check only affects its own
package: that row shows "check failing" for subscribers, and keeps its last
result.

When a community rule is wrong or stops working, open an issue, or a pull
request fixing it; meanwhile, a rule of your own for that package replaces
it on your dashboard.
