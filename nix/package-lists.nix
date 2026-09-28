# Checks package-lists/ against nixpkgs, mirroring how the sync reads them
# (nixkeeper/tracking.py): an entry is a nixpkgs attribute name, including
# nested ones in sets the channel index covers (haskellPackages.foo), or a
# top-level pname. Catches typos and aliases (python3Packages.foo) at
# `nix flake check` time instead of as a "not in nixpkgs" row after a sync.
#
# pkgs should be imported with config.allowAliases = false: aliases aren't in
# the channel index either.
{ pkgs }:
let
  inherit (pkgs) lib;

  # Sets the channel index descends into: python313Packages yes,
  # python3Packages (an alias for the default version) no.
  indexed = set: (builtins.tryEval (pkgs.${set}.recurseForDerivations or false)).value == true;

  isAttribute =
    name:
    let
      path = lib.splitString "." name;
    in
    if builtins.length path == 1 then
      pkgs ? ${name}
    else
      indexed (builtins.head path) && lib.hasAttrByPath path pkgs;

  # Only evaluated when some entry isn't an attribute name: scanning every
  # top-level package takes ~10 s.
  topLevelPnames = lib.genAttrs (builtins.filter (x: x != null) (
    map (
      attr:
      let
        r = builtins.tryEval (
          let
            p = pkgs.${attr};
          in
          if builtins.isAttrs p && p ? pname then p.pname else null
        );
      in
      if r.success then r.value else null
    ) (builtins.attrNames pkgs)
  )) (_: true);

  githubHandles = lib.genAttrs (map (m: lib.toLower m.github) (
    builtins.filter (m: m ? github) (builtins.attrValues lib.maintainers)
  )) (_: true);
in
rec {
  # [ { entry, reason } ] for everything the sync would get wrong.
  problems =
    lists:
    let
      badHandles = builtins.filter (h: !(githubHandles ? ${lib.toLower h})) lists.maintainers;
      entries = lists.extraPackages;
      duplicates = lib.unique (builtins.filter (e: lib.count (x: x == e) entries > 1) entries);
      unknown = builtins.filter (e: !(isAttribute e) && !(topLevelPnames ? ${e})) (lib.unique entries);
      reason =
        e:
        let
          path = lib.splitString "." e;
        in
        if builtins.length path > 1 && lib.hasAttrByPath path pkgs then
          "${builtins.head path} is an alias the sync can't see; use the versioned set (e.g. python313Packages)"
        else
          "not a nixpkgs attribute or top-level pname";
    in
    map (h: {
      entry = h;
      reason = "maintainers: no nixpkgs maintainer has this GitHub handle";
    }) badHandles
    ++ map (e: {
      entry = e;
      reason = "listed more than once";
    }) duplicates
    ++ map (e: {
      entry = e;
      reason = reason e;
    }) unknown;

  # A derivation that builds only if lists has no problems.
  check =
    lists:
    let
      ps = problems lists;
    in
    if ps == [ ] then
      pkgs.runCommand "package-lists-ok" { } "touch $out"
    else
      throw (
        "package-lists/ has problems:\n"
        + lib.concatMapStrings (p: "  - ${p.entry}: ${p.reason}\n") ps
        + "(checked against this flake's pinned nixpkgs: for a package newer than that, run `nix flake update`)"
      );
}
