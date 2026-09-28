"""nixkeeper: tracks how nixpkgs unstable compares to every other repo
Repology knows about, for a curated set of packages.

`nixkeeper-sync` (nixkeeper/__main__.py) runs one sync: it works out which
packages to track from package-lists/, looks each one up, and writes data/
for the page in docs/.
"""
