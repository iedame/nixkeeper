"""Turning Repology projects into the page's rows."""

from . import config
from .sources.nixpkgs import platforms
from .versions import version_key


def search_term(attr):
    """What the GitHub PR/issue searches look for: the attribute name, with
    versioned sets under the alias nixpkgs titles use."""
    for pattern, alias in config.SEARCH_ALIASES:
        attr = pattern.sub(alias, attr)
    return attr


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
        name = attrs[0] if attrs else proj["name"]
        return [
            make_row(
                proj, name, attrs, nix[0] if nix else None, others, nixpkgs, devel=False
            )
        ]

    # Stable first: the variant Repology calls newest, else the shortest attr
    # (wesnoth before wesnoth-devel). The rest compare against devel versions.
    ordered = sorted(
        groups.values(),
        key=lambda g: (
            not any(e.get("status") == "newest" for e in g),
            min(len(e["srcname"]) for e in g),
            min(e["srcname"] for e in g),
        ),
    )
    rows = []
    for i, group in enumerate(ordered):
        attrs = sorted(e["srcname"] for e in group)
        rows.append(
            make_row(proj, attrs[0], attrs, group[0], others, nixpkgs, devel=i > 0)
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
        "searchTerm": search_term(attrs[0]) if attrs else name,
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
        "repoCount": len(others),
        # A devel variant of a split project, or a version Repology itself
        # classifies as devel (lincity).
        "devel": devel or (nix or {}).get("status") == "devel",
    }
    pkgs = [nixpkgs[a] for a in attrs if a in nixpkgs]
    if pkgs:  # not in nixpkgs: nothing to say about platforms or homepage
        row["platforms"] = platforms(pkgs)
        homepage = next(
            (p["meta"].get("homepage") for p in pkgs if p["meta"].get("homepage")), None
        )
        row["homepage"] = homepage[0] if isinstance(homepage, list) else homepage
    return row


def build_rows(projects, nixpkgs):
    """All rows, sorted by name."""
    rows = []
    for proj in projects.values():
        for row in project_rows(proj, nixpkgs):
            if proj.get("staleSince"):
                row["staleSince"] = proj["staleSince"]  # when its data was last fetched
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
