"""nixpkgs side: the package lists (Nix files), the channel's package index and
revision, where nixpkgs marks packages broken, and where their sources come
from."""

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


def evaluate(revision, system, expr, attrs):
    """expr (a function of legacyPackages, with {attrs} for the attributes as
    JSON) evaluated at the channel's revision for system: its JSON answer.
    Raises with nix's last line of output if that fails."""
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
                expr.replace("{attrs}", json.dumps(attrs)),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(out.stdout)
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        # nix's last line of output says what went wrong.
        lines = (getattr(e, "stderr", None) or "").strip().splitlines()
        raise EvalError(lines[-1] if lines else str(e)) from e


class EvalError(Exception):
    """nixpkgs didn't evaluate (evaluate): the reason, from nix."""


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
            values = evaluate(revision, system, BROKEN_EXPR, attrs)
        except EvalError as e:
            print(
                f"::warning::Couldn't evaluate meta.broken on {system}: {e}",
                file=sys.stderr,
            )
            return {}
        for attr, is_broken in zip(attrs, values, strict=True):
            if is_broken:
                result.setdefault(attr, []).append(system)
    return result


# Where each attribute's source comes from: its version, and its src's
# repository (fetchFromGitHub and the like), tag, rev and first URL; null for
# a field it doesn't have, and for an attribute that doesn't evaluate.
SOURCES_EXPR = """pkgs: map (attr:
  let
    lib = pkgs.lib;
    pkg = lib.attrByPath (lib.splitString "." attr) { } pkgs;
    text = s: f: let r = builtins.tryEval (s.${f} or null);
      in if r.success && builtins.isString r.value then r.value else null;
    srcTry = builtins.tryEval (pkg.src or null);
    src = if srcTry.success && builtins.isAttrs srcTry.value then srcTry.value else { };
    urls = builtins.tryEval (src.urls or [ ]);
    found = {
      version = text pkg "version";
      gitRepoUrl = text src "gitRepoUrl";
      tag = text src "tag";
      rev = text src "rev";
      url = if urls.success && builtins.isList urls.value && urls.value != [ ]
        then builtins.head urls.value else text src "url";
    };
    r = builtins.tryEval (builtins.deepSeq found found);
  in if r.success then r.value else null) (builtins.fromJSON ''{attrs}'')"""


def sources(attrs, revision):
    """{attr: {"version", "gitRepoUrl", "tag", "rev", "url"}} at the channel's
    revision, for x86_64-linux (where sources come from doesn't depend on the
    platform, as a rule); attributes that don't evaluate are left out. Raises
    EvalError if nixpkgs doesn't evaluate."""
    attrs = sorted(attrs)
    values = evaluate(revision, "x86_64-linux", SOURCES_EXPR, attrs)
    return {a: v for a, v in zip(attrs, values, strict=True) if v}


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
