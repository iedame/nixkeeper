"""nixpkgs side: the package lists (Nix files), the channel's package index and
revision, and where nixpkgs marks packages broken."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import brotli

from .. import config


def read_lists(path=None):
    """The package lists: {"maintainers": [...], "extraPackages": [...],
    "updateChecks": {...}, "ignoredUpdates": {...}, "upToDate": {...}, ...}.
    From a JSON file as is, or from the Nix folder (package-lists/) by
    evaluating it."""
    path = path or config.LISTS
    if not os.path.exists(path):
        sys.exit(
            f"No package lists at {path}. Start some with `nixkeeper init "
            "--maintainer <your GitHub handle>`, or point --lists (or "
            "NIXKEEPER_LISTS) at yours."
        )
    if path.endswith(".json"):
        with open(path) as f:
            return json.load(f)
    try:
        result = subprocess.run(
            [
                "nix",
                "eval",
                "--extra-experimental-features",
                "nix-command flakes",
                "--json",
                "-f",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        sys.exit(
            "nixkeeper needs nix on the PATH to read the package lists (or give "
            "it a JSON file of them with --lists)."
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"The package lists at {path} didn't evaluate:\n{e.stderr.strip()}")
    return json.loads(result.stdout)


def channel_revision():
    """The nixpkgs commit the channel (and so the index) was built from, or the
    branch name if it can't be fetched: links then still work, their line
    numbers just may have drifted."""
    req = urllib.request.Request(
        config.NIXPKGS_REVISION_URL, headers={"User-Agent": config.user_agent()}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            revision = resp.read().decode().strip()
    except (urllib.error.URLError, OSError) as e:
        print(f"  couldn't fetch the channel revision ({e})", file=sys.stderr)
        return config.NIXPKGS_BRANCH
    return revision or config.NIXPKGS_BRANCH


# meta.broken of each attribute (null if it doesn't evaluate), on the
# platform of the legacyPackages it's applied to.
BROKEN_EXPR = """pkgs: map (attr:
  let
    pkg = pkgs.lib.attrByPath (pkgs.lib.splitString "." attr) { } pkgs;
    r = builtins.tryEval (pkg.meta.broken or false);
  in if r.success then r.value else null) (builtins.fromJSON ''{attrs}'')"""


def broken(attrs, revision):
    """{attr: [systems where nixpkgs marks it broken]} at the channel's
    revision. The index can't say: it's evaluated for x86_64-linux only, and
    `broken = stdenv.hostPlatform.isDarwin;` is false there. Evaluates nixpkgs
    per platform instead (evaluation only, so darwin works from Linux). Empty
    if that fails: this is extra information, not worth failing the sync."""
    attrs = sorted(attrs)
    result = {}
    for system in config.HYDRA_SYSTEMS:
        try:
            out = subprocess.run(
                [
                    "nix",
                    "eval",
                    "--extra-experimental-features",
                    "nix-command flakes",
                    "--json",
                    f"github:NixOS/nixpkgs/{revision}#legacyPackages.{system}",
                    "--apply",
                    BROKEN_EXPR.replace("{attrs}", json.dumps(attrs)),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            values = json.loads(out.stdout)
        except (subprocess.CalledProcessError, OSError, ValueError) as e:
            # nix's last line of output says what went wrong.
            lines = (getattr(e, "stderr", None) or "").strip().splitlines()
            print(
                f"::warning::Couldn't evaluate meta.broken on {system}: "
                f"{lines[-1] if lines else e}",
                file=sys.stderr,
            )
            return {}
        for attr, is_broken in zip(attrs, values, strict=True):
            if is_broken:
                result.setdefault(attr, []).append(system)
    return result


def load_index():
    """attribute -> package (pname, version, meta) for all of nixos-unstable."""
    print("Downloading nixpkgs package index...", file=sys.stderr)
    req = urllib.request.Request(
        config.NIXPKGS_INDEX_URL, headers={"User-Agent": config.user_agent()}
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
