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
- `.github/workflows/`: `sync.yml` (daily sync), `check.yml` (tests on push)

## Commands

```bash
nix run .#sync          # sync into data/ (alias: nix run .#fetch)
nix fmt                 # format everything (Nix, Python, the page)
nix flake check         # tests, formatting, linters, package-list checks
nix develop -c python3 -m unittest discover -s tests -t .   # tests, quickly
nix eval --json -f package-lists                             # what the lists evaluate to
```

New files must be `git add`ed before Nix sees them.
