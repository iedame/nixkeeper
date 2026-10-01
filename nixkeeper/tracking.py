"""Which packages to track, from the package lists and the nixpkgs index, and
which list each is on."""

# The list of packages tracked through meta.maintainers; the other lists are
# named in package-lists/default.nix.
MAINTAINED = "maintained"


def extra_lists(lists):
    """{list name: entries} from extraPackages: named lists (an attrset), or a
    plain list, which counts as the list "extra"."""
    extra = lists.get("extraPackages") or {}
    return {"extra": extra} if isinstance(extra, list) else extra


def maintained(lists, nixpkgs):
    """Attributes whose meta.maintainers include one of the handles, sorted."""
    handles = {h.lower() for h in lists["maintainers"]}
    return [
        attr
        for attr, p in sorted(nixpkgs.items())
        if any(
            isinstance(m, dict) and (m.get("github") or "").lower() in handles
            for m in p["meta"].get("maintainers") or []
        )
    ]


def by_pname(nixpkgs):
    """pname -> top-level attributes. Bare pnames only match top-level
    packages: "heroic" shouldn't pull in typstPackages.heroic."""
    index = {}
    for attr, p in nixpkgs.items():
        if "." not in attr:
            index.setdefault(p.get("pname"), []).append(attr)
    return index


def extra_attrs(name, nixpkgs, pnames):
    """What an extra entry tracks: an exact attribute name just that package
    (_1password-gui without its -beta, which shares the pname "1password");
    else every top-level package with that pname."""
    return [name] if name in nixpkgs else sorted(pnames.get(name, []))


def tracked_packages(lists, nixpkgs):
    """name -> (nixpkgs attrs to look up, Repology project name to try if none
    of them resolve). Maintained packages go one attr at a time: with nested
    sets a pname can mean unrelated packages (foo, python313Packages.foo)."""
    wanted = {
        attr: ([attr], nixpkgs[attr].get("pname") or attr)
        for attr in maintained(lists, nixpkgs)
    }
    pnames = by_pname(nixpkgs)
    entries = {e for es in extra_lists(lists).values() for e in es}
    for name in sorted(entries):
        attrs = extra_attrs(name, nixpkgs, pnames)
        # Not in nixpkgs: tracked anyway, as a "not in nixpkgs" row, and
        # reported with the lists (listcheck.py).
        wanted.setdefault(name, (attrs, name))
    return wanted


def list_names(lists, nixpkgs):
    """Which lists each attribute is on (or, for an entry not in nixpkgs, the
    entry's name): {name: [list names]}."""
    found = {attr: [MAINTAINED] for attr in maintained(lists, nixpkgs)}
    pnames = by_pname(nixpkgs)
    for list_name, entries in extra_lists(lists).items():
        for name in entries:
            for key in extra_attrs(name, nixpkgs, pnames) or [name]:
                if list_name not in found.setdefault(key, []):
                    found[key].append(list_name)
    return found


def add_lists(rows, names):
    """Give each row the lists it's on ("lists"): those of its attributes, or
    of its own name when it's not in nixpkgs. "maintained" first, then the
    named lists alphabetically."""
    for row in rows:
        on = {n for key in [*row["attrs"], row["name"]] for n in names.get(key, [])}
        row["lists"] = sorted(on, key=lambda n: (n != MAINTAINED, n))
