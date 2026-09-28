"""Which packages to track, from the package lists and the nixpkgs index."""

import sys


def tracked_packages(lists, nixpkgs):
    """name -> (nixpkgs attrs to look up, Repology project name to try if none
    of them resolve). Maintained packages go one attr at a time: with nested
    sets a pname can mean unrelated packages (foo, python313Packages.foo)."""
    wanted = {}
    handles = {h.lower() for h in lists["maintainers"]}
    for attr, p in sorted(nixpkgs.items()):
        if any(
            isinstance(m, dict) and (m.get("github") or "").lower() in handles
            for m in p["meta"].get("maintainers") or []
        ):
            wanted[attr] = ([attr], p.get("pname") or attr)
    # Bare pnames only match top-level packages: "heroic" shouldn't pull in
    # typstPackages.heroic.
    by_pname = {}
    for attr, p in nixpkgs.items():
        if "." not in attr:
            by_pname.setdefault(p.get("pname"), []).append(attr)
    for name in lists["extraPackages"]:
        # An exact attribute name tracks just that package (_1password-gui
        # without its -beta, which shares the pname "1password").
        attrs = [name] if name in nixpkgs else sorted(by_pname.get(name, []))
        if not attrs:
            print(
                f"  {name} is neither a nixpkgs attribute nor a top-level pname "
                "(aliases like python3Packages need their versioned name)",
                file=sys.stderr,
            )
        wanted.setdefault(name, (attrs, name))
    return wanted
