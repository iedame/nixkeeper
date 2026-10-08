# Checks notifications/'s format (nixkeeper/notify.py reads it): each file
# in maintainers/ is { maintainer = "<GitHub handle>"; }, each in teams/
# { team = "<team shortName>"; mention = [ handles ]; }, named after its
# maintainer or team (as a list's file name: Qt-KDE -> qt-kde.nix). Whether
# the handles and teams exist is checked on pull requests against
# nixos-unstable (scripts/check-notifications.py, with the consent rule:
# only adding yourself), not here: this flake's nixpkgs lags it, so a new
# maintainer or team would fail until the lock moves.
{ pkgs }:
let
  inherit (pkgs) lib;

  # As datastore.slug: "Security review" -> "security-review".
  slug =
    name:
    lib.pipe (lib.toLower name) [
      (builtins.split "[^a-z0-9]+")
      (builtins.filter builtins.isString)
      (builtins.filter (s: s != ""))
      (lib.concatStringsSep "-")
    ];

  # notifications/'s folders, and the field each file in them has.
  folders = {
    maintainers = "maintainer";
    teams = "team";
  };

  problemsOf =
    folder: name: sub:
    let
      at = reason: "${folder}/${name}.nix: ${reason}";
      wanted = folders.${folder};
      fields = builtins.attrNames sub;
      kind = builtins.filter (k: sub ? ${k}) [
        "maintainer"
        "team"
      ];
      who = sub.${builtins.head kind};
      mention = sub.mention or [ ];
    in
    if !builtins.isAttrs sub then
      [ (at "should be an attribute set") ]
    else if kind != [ wanted ] then
      [ (at "needs ${wanted} (and only that: this is ${folder}/)") ]
    else
      map (k: at "unknown field ${k} (maintainer, team, mention)") (
        lib.subtractLists [
          "maintainer"
          "team"
          "mention"
        ] fields
      )
      ++ lib.optional (!builtins.isString who) (at "${builtins.head kind} should be a string")
      ++ lib.optional (builtins.isString who && slug who != name) (
        at "should be named ${slug who}.nix, after its ${builtins.head kind}"
      )
      ++ lib.optional (sub ? maintainer && sub ? mention) (
        at "a maintainer's issue mentions the maintainer: no mention"
      )
      ++ lib.optional (!builtins.isList mention) (at "mention should be a list of handles")
      ++ lib.optional (builtins.isList mention && !(builtins.all builtins.isString mention)) (
        at "mention should be a list of handles (strings)"
      );
in
{
  problems =
    subs:
    lib.concatLists (
      lib.mapAttrsToList (folder: files: lib.concatLists (lib.mapAttrsToList (problemsOf folder) files)) (
        builtins.intersectAttrs folders subs
      )
    )
    ++ map (f: "${f}: not a folder notifications/ reads (maintainers, teams)") (
      builtins.attrNames (removeAttrs subs (builtins.attrNames folders))
    );
  check =
    subs:
    let
      found = (import ./notifications.nix { inherit pkgs; }).problems subs;
    in
    if found != [ ] then
      throw ("notifications/ has problems:\n" + lib.concatMapStrings (p: "  - ${p}\n") found)
    else
      pkgs.runCommand "nixkeeper-notifications-ok" { } "touch $out";
}
