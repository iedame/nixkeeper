"""Community update checks (community/update-checks.nix): rules anyone can
contribute by PR, for any nixpkgs package. Opt in with `communityChecks =
true;` in the package lists; then each sync uses the rules for the packages
it tracks, your own update checks winning over the community's for the same
package. The rules come with nixkeeper (the version you have pinned): new ones
arrive when you update it, never in between.

Community rules run on every subscriber's machine, so they're held to limits
your own rules aren't (safety(), and http.get's safe mode): an unsafe rule is
refused and reported, never fetched."""

import ipaddress
import json
import os
import re
import subprocess
import sys
from importlib import resources
from urllib.parse import urlsplit

# Where the package carries the file (copied in from community/ when it's
# built), and where a checkout has it.
_PACKAGED = resources.files("nixkeeper") / "community" / "update-checks.nix"
_CHECKOUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "community", "update-checks.nix"
)

# The fields a community rule may have (as your own rules: github + tags,
# github + branch (+ outdatedAfter), or url + pattern, and frequent).
FIELDS = {"github", "tags", "branch", "outdatedAfter", "url", "pattern", "frequent"}
# A GitHub owner (letters, digits, hyphens) and repository (not "." or "..").
GITHUB_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/(?!\.\.?$)[A-Za-z0-9_.-]+$")
# Hostnames that only mean something on a local network.
LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
MAX_PATTERN = 200
# A group with a repeat inside that is repeated itself, like (a+)+ or (\w*)*:
# the shape that can take a very long time on a page that almost matches.
NESTED_REPEAT = re.compile(r"\((?:[^()\\]|\\.)*[+*}](?:[^()\\]|\\.)*\)[+*{]")


def path():
    """The community file: the package's copy, or a checkout's."""
    if _PACKAGED.is_file():
        return str(_PACKAGED)
    return os.path.normpath(_CHECKOUT)


def rules(file=None):
    """{package name: rule}, from the community file (evaluated with Nix), or
    {} with a warning if it can't be read."""
    file = file or path()
    try:
        result = subprocess.run(
            [
                "nix",
                "eval",
                "--extra-experimental-features",
                "nix-command flakes",
                "--json",
                "-f",
                file,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        detail = getattr(e, "stderr", None) or e
        print(
            f"::warning::community update checks: couldn't read {file} ({detail})",
            file=sys.stderr,
        )
        return {}


def merge(lists, tracked):
    """The update checks to run: your own, plus the community's for packages
    you track and have no rule of your own for (only when the lists say
    `communityChecks = true;`). Returns (checks, names of the community ones)."""
    own = lists.get("updateChecks") or {}
    if lists.get("communityChecks") is not True:
        return own, set()
    community = {
        name: rule
        for name, rule in rules().items()
        if name in set(tracked) and name not in own
    }
    if community:
        print(
            f"Community update checks for: {', '.join(sorted(community))}",
            file=sys.stderr,
        )
    return {**own, **community}, set(community)


def is_public_host(host):
    """Whether host is a name or address on the public internet: not an IP
    address written out, not localhost or a local-network name."""
    host = (host or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(LOCAL_SUFFIXES):
        return False
    try:
        ipaddress.ip_address(host.strip("[]"))
        return False  # an address written out, not a name
    except ValueError:
        return "." in host


def safety(rule):
    """Why a community rule can't run, or None if it can."""
    if not isinstance(rule, dict):
        return "not a rule"
    unknown = set(rule) - FIELDS
    if unknown:
        return f"unknown field {', '.join(sorted(unknown))}"
    if "github" in rule and not GITHUB_REPO.match(str(rule["github"])):
        return 'github must be "owner/repo"'
    if "url" in rule:
        parts = urlsplit(str(rule["url"]))
        if parts.scheme != "https":
            return "url must be https://"
        if parts.port not in (None, 443) or parts.username or parts.password:
            return "url can't name a port or credentials"
        if not is_public_host(parts.hostname):
            return "url must name a public host, not an address or local name"
    for field in ("tags", "pattern"):
        pattern = rule.get(field)
        if pattern is None:
            continue
        if not isinstance(pattern, str) or len(pattern) > MAX_PATTERN:
            return f"{field} must be a pattern of at most {MAX_PATTERN} characters"
        if NESTED_REPEAT.search(pattern) or re.search(r"\\[1-9]", pattern):
            return f"{field} repeats a repeat or refers back to a group: too slow"
    return None
