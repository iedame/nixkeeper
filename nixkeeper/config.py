"""Settings shared across nixkeeper. Modules read these as config.NAME at call
time, so tests can patch them."""

import os
import re

# Where things live, and how to notify. The `nixkeeper` command (cli.py) sets
# these from its flags, which win over these environment variables, which win
# over the defaults: the user's own folders (XDG), so the installed command
# works from anywhere. From a checkout, the flake's apps (nix run .#sync)
# pass --lists package-lists --data-dir data instead.
#
# NIXKEEPER_DATA_DIR (--data-dir): the published data (the page's data/), also
#   where the next run finds the previous one. Default:
#   ~/.local/state/nixkeeper/data ($XDG_STATE_HOME).
# NIXKEEPER_LISTS (--lists): the package lists, as the Nix folder
#   (package-lists/, evaluated with nix) or as a JSON file of what it
#   evaluates to. Default: ~/.config/nixkeeper/package-lists, or lists.json
#   there if that's what exists ($XDG_CONFIG_HOME).
# NIXKEEPER_NOTIFY (--notify): how to report what changed (notify.py).
# NIXKEEPER_CONTACT: how the people who run this copy can be reached (an
#   email or a URL), added to the User-Agent; see user_agent().


def _xdg(variable, fallback):
    """An XDG base folder: the variable if it's an absolute path (the spec
    ignores relative ones), else ~/fallback."""
    value = os.environ.get(variable, "")
    return value if os.path.isabs(value) else os.path.expanduser(f"~/{fallback}")


CONFIG_DIR = os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), "nixkeeper")
STATE_DIR = os.path.join(_xdg("XDG_STATE_HOME", ".local/state"), "nixkeeper")


def _default_lists():
    folder = os.path.join(CONFIG_DIR, "package-lists")
    json_file = os.path.join(CONFIG_DIR, "lists.json")
    return (
        json_file
        if not os.path.exists(folder) and os.path.exists(json_file)
        else folder
    )


DEFAULTS = {
    "OUT_DIR": os.path.join(STATE_DIR, "data"),
    "LISTS": _default_lists(),
    "NOTIFY": "none",
}
OUT_DIR = os.environ.get("NIXKEEPER_DATA_DIR") or DEFAULTS["OUT_DIR"]
LISTS = os.environ.get("NIXKEEPER_LISTS") or DEFAULTS["LISTS"]
NOTIFY = None  # set by the command; otherwise NIXKEEPER_NOTIFY, read when used
NIX_REPO = "nix_unstable"
UPSTREAM_URL = "https://github.com/iedame/nixkeeper"
CONTACT_MAX = 100  # characters of NIXKEEPER_CONTACT kept in the User-Agent


def user_agent():
    """How nixkeeper introduces itself to every source, as API etiquette asks:
    the software, its version and where it lives (the same for every copy:
    a fix belongs there), then who runs this copy, where that's public or
    chosen: the repository running it on GitHub Actions (public anyway), and
    NIXKEEPER_CONTACT. A personal machine adds nothing unless asked.

      nixkeeper/0.9.0 (+https://github.com/iedame/nixkeeper; someone/nixkeeper)
    """
    from . import version  # here: nixkeeper/__init__.py imports nothing back

    who = []
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and repo
        and not UPSTREAM_URL.endswith(f"/{repo}")
    ):
        who.append(repo)
    contact = _comment_safe(os.environ.get("NIXKEEPER_CONTACT", ""))
    if contact:
        who.append(contact)
    return f"nixkeeper/{version()} ({'; '.join([f'+{UPSTREAM_URL}', *who])})"


def _comment_safe(text):
    """text fit for the User-Agent's comment: printable ASCII only (no line
    breaks: they'd start a new header), no parentheses or semicolons (they'd
    end the comment or a part of it), spaces collapsed, at most CONTACT_MAX
    characters."""
    text = re.sub(r"[^\x20-\x7e]|[();]", " ", text)
    return " ".join(text.split())[:CONTACT_MAX].strip()


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
# A server that answers "too many requests" or "unavailable" may say how long
# to wait (Retry-After): nixkeeper waits that long, up to this many seconds.
# Asked to wait longer, it gives that request up instead of stalling the run
# (the package keeps its previous data, as with any failed lookup).
MAX_RETRY_AFTER = 300
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
# A Hydra job with nothing going on (built OK, its package up to date and
# unchanged) is asked about every this many days, not daily: a third of them
# each day (hydra.due).
HYDRA_QUIET_DAYS = 3

# Logs of nixpkgs-update (the r-ryantm bot): one directory per attribute, one
# log per attempt (<attr>/<YYYY-MM-DD>.log). It tries each package every ten
# days or so. Moved from nixpkgs-update-logs.nix-community.org in 2026.
NIXPKGS_UPDATE_LOGS_URL = "https://nixpkgs-update-logs.nixos.org"
# After this many lookups in a row fail, the log site is likely down (as for
# Hydra).
UPDATE_LOGS_MAX_CONSECUTIVE_FAILURES = 3

GITHUB_REPO = "NixOS/nixpkgs"
GITHUB_SEARCH_BATCH = 20  # searches per GraphQL request
# nixpkgs PR/issue titles name packages in versioned sets by their alias
# ("python3Packages.requests: 2.34 -> 2.35"), which the index doesn't carry.
SEARCH_ALIASES = [
    (re.compile(r"^python3\d+Packages\."), "python3Packages."),
]
