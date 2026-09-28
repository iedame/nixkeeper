# nixkeeper

Tracks how nixpkgs unstable compares to every other repo Repology knows about,
for a curated set of packages, and shows it on a static page (`docs/`).

## What gets tracked

`package-lists/default.nix` lists GitHub handles under `maintainers` (every
nixpkgs package they maintain is tracked) and imports further lists of
nixpkgs attribute names (exactly that package, e.g. `haskellPackages.pandoc`)
or pnames (every top-level package with that pname).

## Layout

- `nixkeeper/`: the sync, as a Python package
  - `sources/`: nixpkgs index + package lists, Repology, GitHub
  - `tracking.py` → `lookup.py` → `rows.py` → `history.py` → `output.py`,
    run in that order by `__main__.py`
- `tests/`: offline tests, one file per module
- `nix/package-lists.nix`: `nix flake check` validates the package lists
  against nixpkgs (typos, aliases like `python3Packages`, unknown maintainer
  handles, duplicates)
- `docs/`: the page (`index.html`, `app.js`, `style.css`), reading `data/` from the `data` branch
- `.github/workflows/`: `sync.yml` (daily sync), `quick-check.yml` (hourly
  frequent update checks), `check.yml` (tests on push)

## Commands

```bash
nix run .#sync          # sync into data/ (alias: nix run .#fetch)
nix run .#quick-check   # only the frequent update checks, against data/ (hourly in CI)
nix fmt                 # format everything (Nix, Python, the page)
nix flake check         # tests, formatting, linters, package-list checks
nix develop -c python3 -m unittest discover -s tests -t .   # tests, quickly
nix eval --json -f package-lists                             # what the lists evaluate to
```

New files must be `git add`ed before Nix sees them.

## Running elsewhere

Everything defaults to running from a checkout with the GitHub workflows.
Elsewhere (a server, a service), these environment variables change that:

| Variable | Default | What it sets |
|---|---|---|
| `NIXKEEPER_DATA_DIR` | `data` | where the data is written, and the previous run read from |
| `NIXKEEPER_LISTS` | `package-lists` | the package lists: that Nix folder, or a JSON file of what it evaluates to |
| `NIXKEEPER_GITHUB_TOKEN_FILE` | – | a file holding a GitHub token (else `GITHUB_TOKEN`, else the local `gh` login) |
| `NIXKEEPER_NOTIFY` | `none` | `github-issue` to keep the status issue up to date (the workflows set it) |
| `NIXKEEPER_GITHUB_REPO` | the workflow's repo | where the status issue lives |
| `NIXKEEPER_PAGE_URL` | the GitHub Pages site | the page link in notifications |

The status issue is only posted with a token given explicitly (the token file
or `GITHUB_TOKEN`), never with the local `gh` login.

The page finds its data by itself when `data/` is served next to it. Otherwise
it reads the repository's `data` branch on a GitHub Pages site, or wherever
`<meta name="nixkeeper-data" content="…">` in `docs/index.html` points.
`?data=<url>` (same site only) overrides it for testing.

## License

nixkeeper's code is released under the [MIT License](LICENSE).

The published data (the `data` branch) is collected from other projects and
remains subject to their terms: [Repology](https://repology.org), nixpkgs'
[channel index](https://channels.nixos.org), [Hydra](https://hydra.nixos.org),
the [nixpkgs-update logs](https://nixpkgs-update-logs.nixos.org), GitHub, and
the release pages named in `package-lists/update-checks.nix`.

Fetching the nixpkgs-update logs follows the approach of
[nixpkgs-update-notifier](https://github.com/asymmetric/nixpkgs-update-notifier),
reimplemented here.
