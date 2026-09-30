"""nixkeeper: a health dashboard for the nixpkgs packages you maintain: new
releases, build and update failures, and vulnerabilities, in one place.

`nixkeeper-sync` (nixkeeper/__main__.py) runs one sync: it works out which
packages to track from package-lists/, gathers what every source says about
them, and writes data/ for the page in docs/. The hourly checks
(`nixkeeper-frequent-check`, `nixkeeper-pr-check`) refresh a few rows of the
last published data. CONTRIBUTING.md maps the modules.
"""
