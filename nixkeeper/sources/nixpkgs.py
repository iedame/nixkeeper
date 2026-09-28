"""nixpkgs side: the package lists (Nix files) and the channel's package index."""

import json
import subprocess
import sys
import urllib.request

import brotli

from .. import config


def read_lists():
    """package-lists/default.nix, evaluated:
    {"maintainers": [...], "extraPackages": [...]}."""
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--extra-experimental-features",
            "nix-command flakes",
            "--json",
            "-f",
            config.LISTS_DIR,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def load_index():
    """attribute -> package (pname, version, meta) for all of nixos-unstable."""
    print("Downloading nixpkgs package index...", file=sys.stderr)
    req = urllib.request.Request(
        config.NIXPKGS_INDEX_URL, headers={"User-Agent": config.USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        # Includes nested sets (haskellPackages.foo), but not aliases such as
        # python3Packages: those need their versioned name (python313Packages).
        return json.loads(brotli.decompress(resp.read()))["packages"]


def platforms(pkgs):
    """Whether any of pkgs builds on Linux / macOS, from meta.platforms. None
    when none of them declares platforms: nixpkgs then doesn't restrict it."""
    declared = [p["meta"]["platforms"] for p in pkgs if p["meta"].get("platforms")]
    if not declared:
        return None
    systems = [s for ps in declared for s in ps if isinstance(s, str)]
    return {
        "linux": any(s.endswith("-linux") for s in systems),
        "darwin": any(s.endswith("-darwin") for s in systems),
    }
