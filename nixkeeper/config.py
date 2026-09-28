"""Settings shared across nixkeeper. Modules read these as config.NAME at call
time, so tests can patch them."""

import os
import re

OUT_DIR = "data"
LISTS_DIR = "package-lists"
NIX_REPO = "nix_unstable"
USER_AGENT = "nixkeeper/1.0 (personal package tracker)"

# Every package in nixos-unstable with its meta (maintainers, platforms, ...).
# Same channel Repology's nix_unstable tracks, and far cheaper than evaluating
# nixpkgs ourselves.
NIXPKGS_INDEX_URL = "https://channels.nixos.org/nixos-unstable/packages.json.br"
# The nixpkgs commit that channel was built from: source links point there, so
# their line numbers match the data even after the files change.
NIXPKGS_REVISION_URL = "https://channels.nixos.org/nixos-unstable/git-revision"
NIXPKGS_BRANCH = "nixos-unstable"  # link target if the revision can't be fetched
NIXPKGS_SOURCE_URL = "https://github.com/NixOS/nixpkgs/blob/{revision}/{path}"

# repology.org has occasionally been unreachable; repology.amdmi3.ru (the
# author's own domain) has served as a working fallback. Tried in order;
# set REPOLOGY_BASE_URL to force a single one instead.
_override = os.environ.get("REPOLOGY_BASE_URL")
REPOLOGY_URLS = (
    [_override] if _override else ["https://repology.org", "https://repology.amdmi3.ru"]
)
RETRY_DELAYS = [5, 15]  # seconds before each retry of a failed Repology request
# If more lookups than this fail, Repology is likely down: abort and keep the
# previous data (the page flags it as stale) instead of publishing a run that's
# mostly "not refreshed".
MAX_FAILED_SHARE = 0.5

# Repology statuses the page shows as outdated ("legacy": outdated while the
# same repo has a newer version in another package).
OUTDATED_STATUSES = {"outdated", "legacy"}

# Hydra, nixpkgs' build farm. The nixpkgs/unstable jobset builds master (not the
# nixos-unstable channel, which only advances once enough of it has built).
HYDRA_URL = "https://hydra.nixos.org"
HYDRA_PROJECT = "nixpkgs"
HYDRA_JOBSET = "unstable"
# Platforms nixpkgs builds; x86_64-darwin is no longer one of them.
HYDRA_SYSTEMS = ["x86_64-linux", "aarch64-linux", "aarch64-darwin"]
# After this many lookups in a row fail, Hydra is likely down: the rest of the
# run reuses the previous run's results instead of retrying each job.
HYDRA_MAX_CONSECUTIVE_FAILURES = 3

GITHUB_REPO = "NixOS/nixpkgs"
GITHUB_SEARCH_BATCH = 20  # searches per GraphQL request
# nixpkgs PR/issue titles name packages in versioned sets by their alias
# ("python3Packages.requests: 2.34 -> 2.35"), which the index doesn't carry.
SEARCH_ALIASES = [
    (re.compile(r"^python3\d+Packages\."), "python3Packages."),
]
