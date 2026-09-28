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

  # Whether the sync tracks a row of this name: listed itself, listed by
  # pname, or maintained by one of the handles (see nixkeeper/tracking.py).
  isTracked =
    lists: name:
    let
      pkg = lib.attrByPath (lib.splitString "." name) null pkgs;
      meta = (builtins.tryEval (if builtins.isAttrs pkg then pkg.meta or { } else { })).value;
      handles = map lib.toLower lists.maintainers;
    in
    builtins.elem name lists.extraPackages
    || (
      isAttribute name
      && (
        builtins.elem (pkg.pname or null) lists.extraPackages
        || builtins.any (m: builtins.elem (lib.toLower (m.github or "")) handles) (meta.maintainers or [ ])
      )
    );

  checkProblems =
    lists: name: check:
    let
      at = reason: {
        entry = "updateChecks.${name}";
        inherit reason;
      };
      # A check is github + tags, or url + pattern.
      kind =
        fields: valid:
        lib.optional (!builtins.isString (check.${builtins.elemAt fields 1} or null)) (
          at "${builtins.elemAt fields 1} must be a regex string"
        )
        ++ lib.optional (!valid) (
          at (
            if check ? github then
              ''github must be "owner/repo"''
            else
              "url must start with https:// or http://"
          )
        )
        ++ map (k: at "unknown field ${k}") (
          builtins.filter (k: !builtins.elem k fields) (builtins.attrNames check)
        );
    in
    lib.optional (!isTracked lists name) (at "not a tracked package (use its row name, the attribute)")
    ++ (
      if check ? github && check ? url then
        [ (at "use either github (+ tags) or url (+ pattern), not both") ]
      else if check ? github then
        kind [ "github" "tags" ] (builtins.match "[^/ ]+/[^/ ]+" check.github != null)
      else if check ? url then
        kind [ "url" "pattern" ] (builtins.match "https?://.+" check.url != null)
      else
        [ (at "needs github + tags, or url + pattern") ]
    );
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
    }) unknown
    ++ lib.concatLists (lib.mapAttrsToList (checkProblems lists) (lists.updateChecks or { }));

  # A derivation that builds only if lists has no problems. The update checks'
  # tag patterns are Python regexes, so Python compiles them.
  check =
    lists:
    let
      ps = problems lists;
    in
    if ps == [ ] then
      pkgs.runCommand "package-lists-ok"
        {
          nativeBuildInputs = [ pkgs.python3 ];
          checks = builtins.toJSON (lists.updateChecks or { });
          passAsFile = [ "checks" ];
        }
        ''
          python3 - "$checksPath" <<'EOF'
          import json, re, sys
          bad = []
          for name, check in json.load(open(sys.argv[1])).items():
              field = "tags" if "github" in check else "pattern"
              try:
                  if re.compile(check[field]).groups > 1:
                      bad.append(f"{name}: {field} has more than one capture group")
              except re.error as e:
                  bad.append(f"{name}: {field} is not a valid regex ({e})")
          if bad:
              sys.exit("package-lists/update-checks.nix has problems:\n  - " + "\n  - ".join(bad))
          EOF
          touch $out
        ''
    else
      throw (
        "package-lists/ has problems:\n"
        + lib.concatMapStrings (p: "  - ${p.entry}: ${p.reason}\n") ps
        + "(checked against this flake's pinned nixpkgs: for a package newer than that, run `nix flake update`)"
      );
}
