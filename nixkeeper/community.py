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


def problems(rules):
    """What's wrong with community rules beyond their format (which
    nix/package-lists.nix checks): the limits, and the patterns as Python
    compiles them. For CI: ["name: why", ...]."""
    found = []
    for name, rule in sorted(rules.items()):
        if why := safety(rule):
            found.append(f"{name}: {why}")
            continue
        for field in ("tags", "pattern"):
            if field in rule:
                try:
                    if re.compile(rule[field]).groups > 1:
                        found.append(f"{name}: {field} has more than one capture group")
                except re.error as e:
                    found.append(f"{name}: {field} is not a valid regex ({e})")
    return found


def run(names=None, file=None):
    """Run community rules for real, as a sync would (`nixkeeper
    community-check`): every rule, or those named, against nixpkgs'
    current versions. Returns {name: (version found or None, why not)}."""
    from datetime import UTC, datetime

    from .sources import nixpkgs as nixpkgs_source
    from .sources import upstream

    all_rules = rules(file)
    unknown = sorted(set(names or ()) - set(all_rules))
    chosen = {n: r for n, r in all_rules.items() if not names or n in names}
    index = nixpkgs_source.load_index()
    results = {n: (None, "no community rule of that name") for n in unknown}
    rows = []
    for name in chosen:
        if name not in index:
            results[name] = (None, "not in nixpkgs' channel index")
            continue
        version = index[name].get("version")
        rows.append({"name": name, "nixVersion": version, "refVersion": version})
    now = datetime.now(UTC).isoformat()
    upstream.add_checks(rows, chosen, {"packages": []}, now, set(chosen))
    for row in rows:
        failing = (row.get("notRefreshed") or {}).get("upstream")
        if failing:
            results[row["name"]] = (None, failing["reason"])
        else:
            results[row["name"]] = (row["upstream"]["version"], None)
    return results


def report(results):
    """Print run()'s results, and as a GitHub Actions job summary when there
    is one. Returns how many failed."""
    lines = ["| Package | Found | Problem |", "|---|---|---|"]
    failed = 0
    for name, (version, why) in sorted(results.items()):
        print(f"  {name}: {version or 'FAILED'}{f' ({why})' if why else ''}")
        lines.append(f"| {name} | {version or '–'} | {why or ''} |")
        failed += why is not None
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Community update checks\n\n" + "\n".join(lines) + "\n")
    return failed


def changed(base_file):
    """The rules added or changed since base_file (main's community file, for
    a pull request): only those are tried there, so a PR isn't failed by a
    rule it didn't touch."""
    base = rules(base_file)
    return sorted(name for name, rule in rules().items() if base.get(name) != rule)


# The community checks' own status issue: which rules are broken, since when.
ISSUE_LABEL = "nixkeeper-community-status"
ISSUE_TITLE = "Community update checks status"
# The record of broken rules, kept in the issue's body between runs.
STATE = re.compile(r"<!-- nixkeeper-community-state (\{.*?\}) -->", re.S)


def track(results, previous, now):
    """The new record of broken rules ({name: {"since", "reason"}}) from a
    run's results and the previous record, and what changed: (record, newly
    broken names, recovered names)."""
    broken = {}
    for name, (_, why) in results.items():
        if why is not None:
            since = (previous.get(name) or {}).get("since") or now
            broken[name] = {"since": since, "reason": why}
    newly = sorted(set(broken) - set(previous))
    recovered = sorted(n for n in set(previous) - set(broken) if n in results)
    return broken, newly, recovered


def issue_body(results, broken, now):
    total = len(results)
    lines = [
        "The community update checks (`community/update-checks.nix`), run weekly by "
        'the "Community: update checks still work" workflow. Rewritten by each run.',
        "",
    ]
    if broken:
        lines += [
            f"**{len(broken)} of {total} broken:**",
            "",
            "| Rule | Broken since | Why |",
            "|---|---|---|",
        ]
        lines += [
            f"| `{name}` | {info['since'][:10]} | {info['reason'].replace('|', '/')} |"
            for name, info in sorted(broken.items())
        ]
        lines += [
            "",
            "Fix or remove them in `community/update-checks.nix`; until then, each "
            'shows as "check failing" on that package\'s row for subscribers.',
        ]
    else:
        lines.append(f"**All {total} work.**")
    record = json.dumps(broken, sort_keys=True)
    lines += ["", f"_Last run: {now[:16].replace('T', ' ')} UTC._", ""]
    lines.append(f"<!-- nixkeeper-community-state {record} -->")
    return "\n".join(lines)


def publish(results, now=None):
    """Update the community checks' status issue with a run's results (in the
    repository NIXKEEPER_GITHUB_REPO or the workflow's own), commenting when a
    rule newly breaks or recovers. Needs a token given explicitly, never the
    local gh login."""
    from datetime import UTC, datetime

    from .sources import github

    now = now or datetime.now(UTC).isoformat()
    repo = os.environ.get("NIXKEEPER_GITHUB_REPO") or os.environ.get(
        "GITHUB_REPOSITORY"
    )
    token = github.token(use_gh=False)
    if not repo or not token:
        sys.exit(
            "--report-issue needs a repository (NIXKEEPER_GITHUB_REPO) and a token "
            "(NIXKEEPER_GITHUB_TOKEN_FILE or GITHUB_TOKEN)"
        )
    body = github.status_issue_body(repo, token, ISSUE_LABEL) or ""
    match = STATE.search(body)
    previous = json.loads(match.group(1)) if match else {}
    broken, newly, recovered = track(results, previous, now)
    comment = None
    if newly or recovered:
        comment = "\n".join(
            [f"**Broke:** `{n}`: {broken[n]['reason']}" for n in newly]
            + [f"**Works again:** `{n}`" for n in recovered]
        )
    number = github.update_status_issue(
        repo,
        token,
        ISSUE_TITLE,
        issue_body(results, broken, now),
        comment,
        label=ISSUE_LABEL,
        about="The community update checks' status, kept up to date by nixkeeper",
    )
    print(f"Updated issue #{number}", file=sys.stderr)
