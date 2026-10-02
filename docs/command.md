# The nixkeeper command

nixkeeper is one command, `nixkeeper`, with a subcommand for each job (when
something doesn't run as expected, see
[TROUBLESHOOTING.md](troubleshooting.md)):

```bash
nixkeeper init --maintainer <your GitHub handle>   # start your package lists
nixkeeper sync            # one full sync
nixkeeper frequent-check  # only the update checks marked frequent
nixkeeper pr-check        # outdated packages' update PRs
nixkeeper paths           # where the lists and data are, and which setting says so
nixkeeper serve           # show the page on this computer (http://127.0.0.1:8000/)
nixkeeper page <dir>      # write the page and the data into a folder, to host anywhere
```

Without installing it, `nix run github:iedame/nixkeeper -- <command>` runs
the same. To install it, from this repository's flake:

```bash
nix profile install github:iedame/nixkeeper
```

or in a NixOS or home-manager configuration, with the flake as an input
(`inputs.nixkeeper.url = "github:iedame/nixkeeper";`), add
`inputs.nixkeeper.packages.${pkgs.stdenv.hostPlatform.system}.default` to
your packages. It needs `nix` on the `PATH` (it evaluates your lists with
it); `gh` is optional. The old names (`nixkeeper-sync`, ...) still work
until 1.0.

On its own, it keeps your lists in `~/.config/nixkeeper/package-lists/`
(`nixkeeper init` starts them) and the data in
`~/.local/state/nixkeeper/data/` (following `$XDG_CONFIG_HOME` and
`$XDG_STATE_HOME`). From a checkout, `nix run .#sync` (and
`.#frequent-check`, `.#pr-check`) use the checkout's `package-lists/` and
`data/` instead, as the GitHub workflows do. Flags or environment variables
choose others; a flag wins over its variable:

| Flag | Variable | Default | What it sets |
|---|---|---|---|
| `--data-dir` | `NIXKEEPER_DATA_DIR` | `~/.local/state/nixkeeper/data` | where the data is written, and the previous run read from |
| `--lists` | `NIXKEEPER_LISTS` | `~/.config/nixkeeper/package-lists` (or `lists.json` there) | the package lists: that Nix folder, or a JSON file of what it evaluates to |
| | `NIXKEEPER_GITHUB_TOKEN_FILE` | – | a file holding a GitHub token (else `GITHUB_TOKEN`, else the local `gh` login) |
| `--notify` | `NIXKEEPER_NOTIFY` | `none` | `github-issue` to keep the status issue up to date (the workflows set it) |
| | `NIXKEEPER_GITHUB_REPO` | the workflow's repo | where the status issue lives |
| | `NIXKEEPER_PAGE_URL` | the GitHub Pages site | the page link in notifications |
| | `NIXKEEPER_CONTACT` | – | how you can be reached (an email or a URL), added to the User-Agent nixkeeper sends to the sources; see below |
| | `REPOLOGY_BASE_URL` | – | one Repology address to use (normally `repology.org`, falling back to its mirror `repology.amdmi3.ru`) |

nixkeeper introduces itself to every source it reads with a User-Agent
like `nixkeeper/0.9.0 (+https://github.com/iedame/nixkeeper)`: the
software, its version and where it lives, so the people running Repology,
Hydra and the others know what's asking. On GitHub Actions it adds the
repository running it (`; you/nixkeeper`), which is public anyway. On your
own machine it adds nothing more, unless you set `NIXKEEPER_CONTACT`.

The status issue is only posted with a token given explicitly (the token file
or `GITHUB_TOKEN`), never with the local `gh` login. Reading from GitHub (PR
and issue counts, update PRs) does use the `gh` login when there's no other
token.

## Showing the page

The page ships with the command (and in the package's
`share/nixkeeper/www/`). `nixkeeper serve` shows it with the data as it is,
so a new sync appears on the next reload; it listens on this computer only
unless `--bind` says otherwise. `nixkeeper page <dir>` writes a folder for
any static host, with the data copied in as `data/`; run it again after
each sync. It only writes into a new or empty folder, or one it wrote
before.

The page finds its data by itself when `data/` is served next to it. Otherwise
it reads the repository's `data` branch on a GitHub Pages site, or wherever
`<meta name="nixkeeper-data" content="…">` in `page/index.html` points.
`?data=<url>` (same site only) overrides it for testing.

## Pinning a version

A flake input stays on the commit in your `flake.lock`: rebuilding never
changes it, only `nix flake update` does. With the URLs above, that update
takes whatever is on `main` then. Every change there has passed CI (the
tests, both modules evaluated, the NixOS module booted in a VM), but to move
only from release to release, name a version tag:

```nix
inputs.nixkeeper.url = "github:iedame/nixkeeper/v0.9.0";
```

`nix flake update` then leaves it alone; you upgrade by changing the tag,
after reading that release's notes in [CHANGELOG.md](../CHANGELOG.md). Version
tags never move, so a tag always means the same code. The same works for
`nix profile install github:iedame/nixkeeper/v0.9.0`.

With `inputs.nixkeeper.inputs.nixpkgs.follows = "nixpkgs";` (one nixpkgs in
your lock), nixkeeper builds against your nixpkgs rather than the one its CI
tested with; leave it out to build against nixkeeper's own.

To run it as a service instead, see the [NixOS](nixos.md) and
[nix-darwin](darwin.md) modules.
