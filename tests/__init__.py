"""Offline tests for nixkeeper: Repology, GitHub and the nixpkgs index are
replaced by small hand-written samples (tests/helpers.py).

Run with `nix flake check`, or from the repository root inside `nix develop`:
    python3 -m unittest discover -s tests -t .
"""

from nixkeeper import config

# Fake sites answer at once: no waiting between their pages (http.pace), but
# for tests of the pause itself (test_http.py).
config.SITE_PAUSE_SECONDS = 0
