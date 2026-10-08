"""nixkeeper-vulnerabilities' digest (https://github.com/iedame/nixkeeper-
vulnerabilities): what the NixOS security tracker and OSV say about nixpkgs
packages, in one download, read by the daily sync.

Each row gets "vulnerabilities": its CVEs (the tracker's) and advisories
(OSV's), each with a verdict:

- the tracker's issue says "not affected" or "not for us": "dismissed";
  "won't fix": "wontFix" (counted);
- else nixVersion against the CVE record's affected ranges, as nixkeeper
  orders versions: "affected" (counted) in one, "fixed" outside them all.
  The tracker's own status is that same check, but on the version a
  branch had when it last evaluated it, often long ago (2026-10-08: 487
  of its 873 "affected on master" already fixed in nixpkgs): it's used
  only when a range can't be read, "tracker" (counted) when it said
  affected, "fixed" unaffected, "unconfirmed" otherwise;
- OSV's advisories, "osv" (counted), but not for a CVE the tracker has.

A row is vulnerable (changes.is_vulnerable) when one is counted, nixpkgs
marks it insecure, or Repology flags it: the tracker's entries cover some
of a package's CVEs, not necessarily those Repology flags it for, so its
flag stays a source of its own. Without a usable digest, Repology's flag
and nixpkgs' mark decide, as before."""

import gzip
import json
import re
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from ..changes import COUNTED_VULNERABILITIES
from ..versions import version_key
from . import about, http, nixpkgs

FORMAT = 1
# Verdicts that make a row vulnerable: changes.COUNTED_VULNERABILITIES.
COUNTED = COUNTED_VULNERABILITIES
# Worst first: the order a row's list is in, and its worst severity.
SEVERITIES = ("critical", "high", "medium", "moderate", "low")
# The tracker's status of a package, worst first, over a row's attributes.
STATUS_ORDER = ("affected", "unknown", "unaffected", None)
CLAUSE = re.compile(r"(<=|>=|<|>|==|=)\s*v?(\d[\w.+~-]*?)(?:\.\*)?")


def current(meta, now):
    """Why the digest can be used, or None: the tracker read through once
    (complete), and recently (within VULNERABILITIES_DIGEST_MAX_AGE_HOURS)."""
    tracker = meta.get("tracker") or {}
    if not tracker.get("complete") or not tracker.get("readAt"):
        return None
    read = datetime.fromisoformat(tracker["readAt"])
    hours = (datetime.fromisoformat(now) - read) / timedelta(hours=1)
    if hours > config.VULNERABILITIES_DIGEST_MAX_AGE_HOURS:
        return None
    return f"read {hours:.0f} h ago"


def load(now):
    """The digest ({"tracker", "osv"}), or None (saying why) when it's turned
    off, not current or can't be read."""
    base = config.VULNERABILITIES_DIGEST_URL
    if not base:
        return None
    try:
        meta = json.loads(http.get(base + "meta.json") or "null")
        if not meta or meta.get("format") != FORMAT:
            raise ValueError(f"no digest in a format this nixkeeper reads ({base})")
        why = current(meta, now)
        if not why:
            about.note("tracker", False, "not read through yet, or too old")
            print(
                "::warning::Vulnerabilities digest: not used (the tracker not read "
                "through yet, or too old); Repology's flag decides",
                file=sys.stderr,
            )
            return None
        body = http.get_bytes(base + "vulnerabilities.json.gz")
        if body is None:
            raise ValueError("its vulnerabilities.json.gz is missing")
        found = json.loads(gzip.decompress(body))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        about.note("tracker", False, f"couldn't be read ({e})")
        print(
            f"::warning::Vulnerabilities digest: couldn't use it ({e})", file=sys.stderr
        )
        return None
    tracker, osv = meta.get("tracker") or {}, meta.get("osv") or {}
    about.note(
        "tracker",
        True,
        at=tracker.get("readAt"),
        suggestions=tracker.get("suggestions"),
        packages=tracker.get("packages"),
    )
    if osv:
        about.note(
            "osv",
            True,
            at=osv.get("readAt"),
            advisories=osv.get("advisories"),
            packages=osv.get("packages"),
        )
    print(
        f"Vulnerabilities digest: {tracker.get('suggestions'):,} tracker "
        f"suggestions, {osv.get('advisories', 0):,} OSV advisories, {why}",
        file=sys.stderr,
    )
    digest = {"tracker": found.get("tracker") or {}, "osv": found.get("osv") or {}}
    digest["newestRelease"] = newest_release(digest)
    digest["stable"] = stable_versions(digest["newestRelease"])
    return digest


def stable_versions(newest):
    """{attribute: version} of the newest release's channel (its package
    index), or {} when it can't be read (the tracker's status for it is used
    then)."""
    if not newest or not config.STABLE_INDEX_URL:
        return {}
    release = newest.removeprefix("release-")
    url = config.STABLE_INDEX_URL.format(release=release)
    try:
        index = nixpkgs.load_index(url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(
            f"::warning::nixos-{release}'s package index couldn't be read ({e}): "
            "the tracker's status says what's to backport",
            file=sys.stderr,
        )
        return {}
    versions = {a: p["version"] for a, p in index.items() if p.get("version")}
    print(f"  nixos-{release}: {len(versions):,} versions", file=sys.stderr)
    return versions


def newest_release(digest):
    """The newest release branch the tracker evaluates ("release-26.05"),
    by its version, or None: where a fix on master still needs backporting."""
    names = {
        branch
        for s in (digest["tracker"].get("suggestions") or {}).values()
        for p in (s.get("packages") or {}).values()
        for branch in (p.get("branches") or {})
        if branch.startswith("release-")
    }
    return max(
        names, key=lambda b: version_key(b.removeprefix("release-")), default=None
    )


def matches(version, expression):
    """Whether version is in a range as the tracker gives it (from the CVE
    record: "<1.2", "==>= 1.0, < 1.2", "=<1.1", "==1.0", "*"): True, False,
    or None when it can't be read (a list of versions, "x.59.21")."""
    e = (expression or "").strip()
    if e == "*":
        return True
    e = re.sub(r"^===\s*", "==", e)
    if e.startswith("==") and e[2:3] in ("<", ">", "="):
        e = e[2:].strip()  # "==< 1.0": the operator after it
    e = e.replace("=<", "<=").replace("=>", ">=")
    clauses = [c.strip() for c in e.split(",")]
    if not clauses or not all(clauses):
        return None
    key = version_key(version)
    for clause in clauses:
        m = CLAUSE.fullmatch(clause)
        if not m:
            return None
        op, bound = m.group(1), version_key(m.group(2))
        held = {
            "<": key < bound,
            "<=": key <= bound,
            ">": key > bound,
            ">=": key >= bound,
            "==": key == bound,
            "=": key == bound,
        }[op]
        if not held:
            return False
    return True


def by_version(version, affected):
    """ "affected", "fixed" or None (can't tell) for version against a
    suggestion's affected products' ranges ([["affected", "<1.2"],
    ["unaffected", ">=1.2"], ...])."""
    if not version or not affected:
        return None
    hit, cleared, unreadable, any_range = False, False, False, False
    for product in affected:
        for constraint in product.get("versions") or []:
            if not isinstance(constraint, list) or len(constraint) != 2:
                unreadable = True
                continue
            status, expression = constraint
            any_range = True
            found = matches(version, expression)
            if found is None:
                unreadable = True
            elif found and status == "affected":
                hit = True
            elif found and status == "unaffected":
                cleared = True
    if hit and not cleared:
        return "affected"
    if hit or unreadable or not any_range:
        return None  # contradictory, or not all read
    return "fixed"


def tracker_status(row, packages):
    """The tracker's entries for a row's attributes, by suggestion: {id:
    (worst status, its branches)}."""
    found = {}
    for attr in row.get("attrs") or [row["name"]]:
        for entry in packages.get(attr) or []:
            key = entry["suggestion"]
            status = entry.get("status")
            known = found.get(key)
            if known is None or STATUS_ORDER.index(status) < STATUS_ORDER.index(
                known[0]
            ):
                found[key] = (status, attr)
    return found


def releases(suggestion, attr, newest=None, version=None):
    """{release branch: status} of a suggestion's package, master left out
    (what the verdict's from): where a fix may still need backporting. The
    tracker's status for each, but the newest release's by its current
    version against the CVE's ranges, when known and they can be read."""
    branches = (suggestion.get("packages", {}).get(attr) or {}).get("branches") or {}
    found = {b: v.get("status") for b, v in sorted(branches.items()) if b != "master"}
    if newest and version:
        own = by_version(version, suggestion.get("affected"))
        if own:
            found[newest] = "affected" if own == "affected" else "unaffected"
    return found


def verdict(row, suggestion, status, issue):
    """The verdict on one of the tracker's CVEs for a row: its issue's
    verdict when people gave one, else nixVersion against the CVE's ranges,
    else (ranges it can't read) the tracker's last status."""
    issue_status = (issue or {}).get("status")
    if issue_status in ("notAffected", "notForUs"):
        return "dismissed"
    if issue_status == "wontFix":
        return "wontFix"
    found = by_version(row.get("nixVersion"), suggestion.get("affected"))
    if found:
        return found  # "affected" or "fixed"
    return {"affected": "tracker", "unaffected": "fixed"}.get(status, "unconfirmed")


def stable_version(attr, attrs, stable):
    """The newest release's version of a row's package: attr's, else any of
    its attributes'; None when not known."""
    return stable.get(attr) or next((stable[a] for a in attrs if a in stable), None)


def counted_first(entry):
    """Sort key: counted verdicts before the others."""
    return 0 if entry["verdict"] in COUNTED else 1


def severity_rank(entry):
    severity = entry.get("severity")
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def for_row(row, digest):
    """A row's CVEs and advisories with their verdicts ("vulnerabilities"),
    counted ones first, worst severity first; [] when the digest has none."""
    tracker, osv = digest["tracker"], digest["osv"]
    suggestions, issues = tracker.get("suggestions") or {}, tracker.get("issues") or {}
    newest, stable = digest.get("newestRelease"), digest.get("stable") or {}
    attrs = row.get("attrs") or [row["name"]]
    found, cves = {}, set()
    for key, (status, attr) in tracker_status(
        row, tracker.get("packages") or {}
    ).items():
        s = suggestions.get(key)
        if not s:
            continue
        issue = issues.get(s.get("issue")) if s.get("issue") else None
        cve = s.get("cve") or f"suggestion {key}"
        cves.add(cve)
        entry = {
            "id": cve,
            "source": "tracker",
            "verdict": verdict(row, s, status, issue),
            **({"issue": s["issue"]} if s.get("issue") else {}),
            **({"github": issue["github"]} if (issue or {}).get("github") else {}),
            **{k: s[k] for k in ("severity", "score") if s.get(k) is not None},
            **({"summary": s["title"]} if s.get("title") else {}),
            **(
                {"releases": r}
                if (r := releases(s, attr, newest, stable_version(attr, attrs, stable)))
                else {}
            ),
        }
        # Several suggestions for one CVE (several packages): the worst.
        known = found.get(cve)
        if known is None or counted_first(entry) < counted_first(known):
            found[cve] = entry
    advisories = osv.get("advisories") or {}
    for attr in row.get("attrs") or [row["name"]]:
        for advisory in (osv.get("packages") or {}).get(attr) or []:
            a = advisories.get(advisory) or {}
            if advisory in found or cves & set(a.get("cves") or []):
                continue  # the tracker's verdict on that CVE stands
            found[advisory] = {
                "id": advisory,
                "source": "osv",
                "verdict": "osv",
                **({"cves": a["cves"]} if a.get("cves") else {}),
                **({"severity": a["severity"]} if a.get("severity") else {}),
                **({"summary": a["summary"]} if a.get("summary") else {}),
                "ecosystem": a.get("ecosystem"),
            }
    return sorted(
        found.values(), key=lambda e: (counted_first(e), severity_rank(e), e["id"])
    )


def to_backport(found, newest):
    """The CVEs of found (a row's "vulnerabilities") fixed on master but
    still affected on newest, the newest release branch."""
    return [
        v["id"]
        for v in found
        if newest
        and v["verdict"] == "fixed"
        and (v.get("releases") or {}).get(newest) == "affected"
    ]


def add(rows, digest):
    """Give each row its "vulnerabilities" (only when the digest has any for
    it), and "backport": those fixed on master, still affected on the
    newest release branch, when there's a digest. Returns how many rows got
    some."""
    if digest is None:
        return 0
    newest = digest.get("newestRelease") or newest_release(digest)
    n = 0
    for row in rows:
        row.pop("vulnerabilities", None)
        row.pop("backport", None)
        if found := for_row(row, digest):
            row["vulnerabilities"] = found
            if ids := to_backport(found, newest):
                row["backport"] = ids
            n += 1
    return n


def summary(row):
    """The list's view of a row with "vulnerabilities" ("vuln" in its
    summary entry): {"n", "severity"?, "by"} of what's counted, its sources
    with nixpkgs' insecure mark and Repology's flag; None when none says
    so. A row without "vulnerabilities" has no "vuln": Repology's flag and
    nixpkgs' mark decide, as before."""
    counted = [v for v in row["vulnerabilities"] if v["verdict"] in COUNTED]
    by = (
        sorted({v["source"] for v in counted})
        + (["nixpkgs"] if row.get("markedInsecure") else [])
        + (["repology"] if row.get("nixVulnerable") else [])
    )
    if not by:
        return None
    worst = min(counted, key=severity_rank, default={})
    return {
        "n": len(counted),
        **({"severity": worst["severity"]} if worst.get("severity") else {}),
        "by": by,
    }
