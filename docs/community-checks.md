# Community update checks

[Update checks](how-it-works.md#what-gets-tracked) tell nixkeeper about a
new release before Repology counts it as newest: a project's tags, the
branch an unstable version follows, or a release page. Each one is small,
and the same for everyone who tracks that package, so they're worth
sharing: [`community/update-checks.nix`](../community/update-checks.nix) is a
list of them anyone can add to, for any nixpkgs package.

## Using them

Opt in, in your package lists:

```nix
communityChecks = true;
```

That's `package-lists/default.nix` for a dashboard of your own (and the
lists `nixkeeper init` writes), or `lists.communityChecks = true;` in the
[NixOS](nixos.md) or [nix-darwin](darwin.md) module. It's off unless you
turn it on.

Then each sync:

- uses the community rules **only for the packages you track**: the rest are
  never fetched, and never contact anything;
- lets **your own update checks win**: a package with a rule in your
  `updateChecks` uses yours, so you can always override a community rule;
- marks results from a community rule as such, on the page ("a community
  update check found …").

The rules come with nixkeeper itself, so they're pinned like the rest of it:
new ones arrive when you update nixkeeper (or move to a new
[version](command.md#pinning-a-version)), never in between. They're read
with Nix at each sync.

## The limits

Community rules run on everyone's machines who opts in, so they're held to
limits your own rules aren't. A rule beyond them is refused, never fetched,
and shows as "check failing" on its row, with why:

- **Web pages**: `https://` only, to a public host by name. No IP addresses,
  no `localhost` or local-network names, no ports or credentials in the URL.
  The host has to resolve to public internet addresses only, and so does
  every redirect. A page is read up to 2 MB.
- **Patterns** (`tags`, `pattern`): at most 200 characters, with no repeated
  repeats like `(a+)+` and no back-references, which can take a very long
  time to match.
- **Fields**: only the ones the format has (`github`, `tags`, `branch`,
  `outdatedAfter`, `url`, `pattern`, `frequent`); GitHub repositories as
  `owner/repo`.

Your own rules keep their freedom: they're yours, so a page on your own
network is fine there.

## Adding a rule

Open a pull request adding it to
[`community/update-checks.nix`](../community/update-checks.nix), in the same
format as your own update checks (the file's header shows it), keyed by the
package's nixpkgs attribute. A good rule follows what nixpkgs packages (the
stable series it tracks, the page its source comes from), and says in a
comment where the version comes from.

When a community rule is wrong or stops working, open an issue, or a pull
request fixing it; meanwhile, a rule of your own for that package replaces
it on your dashboard.
