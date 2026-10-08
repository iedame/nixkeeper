"""Turning Repology projects into the page's rows."""

import re

from . import config
from .sources.nixpkgs import platforms
from .versions import version_key


def search_term(attr):
    """What the GitHub PR/issue searches look for: the attribute name, with
    versioned sets under the alias nixpkgs titles use."""
    for pattern, alias in config.SEARCH_ALIASES:
        attr = pattern.sub(alias, attr)
    return attr


# An attribute named for a development channel (wesnoth-devel, foo-beta,
# bar_unstable, baz-nightly, code-insiders).
DEVEL_NAME = re.compile(
    r"[-_.](devel|dev|beta|alpha|unstable|nightly|rc|preview|insiders|canary|git)$"
)


def name_blockers(rows):
    """Each dependency-failed build's blockedBy (the digest's: attributes,
    or store names no job builds) as the page links them: [{"name": the
    row named by that attribute, or the attribute or name as it is,
    "row": true when it's a row}]."""
    by_attr = {a: row["name"] for row in rows for a in row.get("attrs") or []}
    for row in rows:
        for build in row.get("builds") or []:
            if build.get("blockedBy") and isinstance(build["blockedBy"][0], str):
                build["blockedBy"] = [
                    {"name": by_attr[a], "row": True} if a in by_attr else {"name": a}
                    for a in build["blockedBy"]
                ]


def row_name(attrs):
    """The attribute a row is named after: the first top-level one, else the
    first (cmake, not azure-sdk-for-cpp.cmake, a set passing it on)."""
    return min(attrs, key=lambda a: ("." in a, a))


def project_rows(proj, nixpkgs):
    """Rows for one Repology project: normally one, but one per version when
    the tracked nixpkgs variants differ (wesnoth / wesnoth-devel). Variants
    sharing a version (heroic / heroic-unwrapped) stay one row."""
    entries = proj["entries"]
    nix_all = [e for e in entries if e.get("repo") == config.NIX_REPO]
    others = [e for e in entries if e.get("repo") != config.NIX_REPO]

    groups = {}  # version -> nix entries of tracked attrs
    for e in nix_all:
        if e.get("srcname") in proj["attrs"]:
            groups.setdefault(e.get("version"), []).append(e)
    if len(groups) < 2:
        nix = next(iter(groups.values()), nix_all)[:1]
        attrs = sorted(proj["attrs"])
        # Named after its nixpkgs attribute, like the lists and GitHub searches;
        # the list entry itself when nixpkgs doesn't have it.
        name = row_name(attrs) if attrs else proj["name"]
        return [
            make_row(
                proj, name, attrs, nix[0] if nix else None, others, nixpkgs, devel=False
            )
        ]

    # Stable first: the variant Repology calls newest, else the shortest attr
    # (wesnoth before wesnoth-devel). The rest are devel variants, compared
    # against devel versions, when they're newer than it or named so
    # (wesnoth-devel, _1password-gui-beta); otherwise older versions kept
    # beside it (gnumake42, php82Extensions.zip).
    ordered = sorted(
        groups.values(),
        key=lambda g: (
            not any(e.get("status") == "newest" for e in g),
            min(len(e["srcname"]) for e in g),
            min(e["srcname"] for e in g),
        ),
    )
    stable = version_key(ordered[0][0].get("version") or "")
    rows = []
    for i, group in enumerate(ordered):
        attrs = sorted(e["srcname"] for e in group)
        devel = i > 0 and (
            version_key(group[0].get("version") or "") > stable
            or any(DEVEL_NAME.search(a) for a in attrs)
        )
        rows.append(
            make_row(
                proj, row_name(attrs), attrs, group[0], others, nixpkgs, devel=devel
            )
        )
    return rows


def make_row(proj, name, attrs, nix, others, nixpkgs, devel):
    def newest(status):
        """The highest version among the other repositories with status."""
        versions = [
            e["version"]
            for e in others
            if e.get("status") == status and e.get("version")
        ]
        return max(versions, key=version_key, default=None)

    row = {
        "name": name,
        # The attribute name, which unlike the pname tells variants apart
        # (_1password-gui and _1password-gui-beta are both pname "1password").
        "searchTerm": search_term(name) if attrs else name,
        "project": proj["project"],
        "dataFile": proj["dataFile"],
        "attrs": attrs,
        "nixVersion": nix.get("version") if nix else None,
        "nixStatus": nix.get("status") if nix else "missing",
        "nixVulnerable": bool(nix.get("vulnerable")) if nix else False,
        # When only Nix packages it (msedgedriver), Repology marks no
        # repository newest, but the one ahead (a stable branch with a
        # backport, say) unique: compared within the family, nixpkgs
        # unstable can still be outdated against it.
        "refVersion": (devel and newest("devel"))
        or newest("newest")
        or newest("unique"),
        # Repositories, not entries: one can list a package several times.
        "repoCount": len({e.get("repo") for e in others}),
        # A devel variant of a split project, or a version Repology itself
        # classifies as devel (lincity).
        "devel": devel or (nix or {}).get("status") == "devel",
    }
    if nix and nix.get("status") == config.KEPT:
        # An older version kept beside a newer one: which, for the page.
        newer = [
            e
            for e in proj["entries"]
            if e.get("repo") == config.NIX_REPO
            and e.get("version")
            and version_key(e["version"]) > version_key(nix.get("version") or "")
        ]
        if newer:
            best = max(version_key(e["version"]) for e in newer)
            # Of those with that version, the plainest name (tracy, not tracy_0_14).
            top = min(
                (e for e in newer if version_key(e["version"]) == best),
                key=lambda e: (len(e.get("srcname") or ""), e.get("srcname") or ""),
            )
            row["keptBeside"] = {"attr": top.get("srcname"), "version": top["version"]}
    pkgs = [nixpkgs[a] for a in attrs if a in nixpkgs]
    if proj.get("unlisted") and pkgs and not nix:
        # In nixpkgs, but not on Repology (read in bulk, with every package):
        # nixpkgs' version, and nothing to compare it with.
        row["nixVersion"] = pkgs[0].get("version")
        row["nixStatus"] = "unlisted"
    if pkgs:  # not in nixpkgs: nothing to say about platforms or homepage
        row["platforms"] = platforms(pkgs)
        homepage = next(
            (p["meta"].get("homepage") for p in pkgs if p["meta"].get("homepage")), None
        )
        row["homepage"] = homepage[0] if isinstance(homepage, list) else homepage
        row["maintainers"] = maintainers(pkgs)
        if found := teams(pkgs):
            row["teams"] = found
        # meta.broken, as the package index has it (x86_64-linux): Hydra's
        # builds say where it's broken, but a broken package often has no
        # Hydra job at all (hydraPlatforms = [], as hackage2nix sets it).
        if any(p["meta"].get("broken") for p in pkgs):
            row["markedBroken"] = True
        # meta.knownVulnerabilities: nixpkgs itself marks it insecure (it
        # won't build without permittedInsecurePackages), with its reasons.
        if found := insecure(pkgs):
            row["markedInsecure"] = found
    return row


def insecure(pkgs):
    """The reasons in pkgs' meta.knownVulnerabilities, each once, in order;
    [] when nixpkgs doesn't mark any of them insecure."""
    found = []
    for p in pkgs:
        for reason in p["meta"].get("knownVulnerabilities") or []:
            if isinstance(reason, str) and reason and reason not in found:
                found.append(reason)
    return found


def maintainers(pkgs):
    """The GitHub handles in pkgs' meta.maintainers, each once (whatever its
    case), in order; [] when none has any (a maintainer without a GitHub
    handle can't be searched for)."""
    found = {}
    for p in pkgs:
        for m in p["meta"].get("maintainers") or []:
            handle = m.get("github") if isinstance(m, dict) else None
            if isinstance(handle, str) and handle:
                found.setdefault(handle.lower(), handle)
    return list(found.values())


def teams(pkgs):
    """The nixpkgs teams in pkgs' meta.teams (maintainers/team-list.nix), by
    their shortName ("Gaming", "Qt-KDE"), each once, in order."""
    found = []
    for p in pkgs:
        for team in p["meta"].get("teams") or []:
            name = team.get("shortName") if isinstance(team, dict) else None
            if isinstance(name, str) and name and name not in found:
                found.append(name)
    return found


def build_rows(projects, nixpkgs):
    """All rows, sorted by name."""
    rows = []
    for proj in projects.values():
        for row in project_rows(proj, nixpkgs):
            if proj.get("staleSince"):
                row["staleSince"] = proj["staleSince"]  # when its data was last fetched
            if proj.get("lookupFailed"):
                row["lookupFailed"] = True  # Repology couldn't be asked: no data
            if proj.get("checkedAt"):
                row["repologyCheckedAt"] = proj["checkedAt"]
            rows.append(row)
    return sorted(rows, key=lambda p: p["name"].lower())


def source_url(position, revision):
    """GitHub link for a meta.position, e.g.
    "pkgs/by-name/we/wesnoth/package.nix:147"."""
    path, _, line = position.rpartition(":")
    if not line.isdigit():
        path, line = position, ""
    url = config.NIXPKGS_SOURCE_URL.format(revision=revision, path=path)
    return f"{url}#L{line}" if line else url


def add_source_links(rows, nixpkgs, revision):
    """Link each row to where nixpkgs defines it: the first of its attrs that
    has a position (packages not in nixpkgs get none)."""
    for row in rows:
        position = next(
            (
                nixpkgs[a]["meta"]["position"]
                for a in row["attrs"]
                if a in nixpkgs and nixpkgs[a]["meta"].get("position")
            ),
            None,
        )
        if position:
            row["source"] = source_url(position, revision)
