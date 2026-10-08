# Who gets a status issue of their own: every .nix file in maintainers/
# and teams/, read by its name. Each opens an issue in this repository,
# rewritten by every daily sync with what needs attention in their packages,
# and a comment (which is what notifies) when something newly does.
# Removing the file closes the issue.
#
#   maintainers/iedame.nix   { maintainer = "iedame"; }
#                            "nixkeeper status: @iedame": the packages
#                            listing that GitHub handle in meta.maintainers;
#                            it's mentioned in the issue, which subscribes it
#
#   teams/gaming.nix         { team = "Gaming"; mention = [ "iedame" ]; }
#                            "nixkeeper status: Gaming team": the packages of
#                            that nixpkgs team (its shortName, as in
#                            maintainers/team-list.nix), and those a list named
#                            after it adds (package-lists/); the handles in
#                            mention are mentioned (a team itself can't be:
#                            it's in another GitHub organisation)
#
# A file's name is its maintainer's handle or its team's name as a file
# name (Qt-KDE: qt-kde.nix); the folders keep a handle and a team of the
# same name apart. Packages in the sets updated in bulk (R, Haskell, ...)
# are left out, as the page's counts leave them out.
#
# By pull request: you can only add yourself. CI checks that every handle a
# changed file newly mentions is the pull request's author
# (docs/notifications.md).
let
  # A folder's .nix files: { <name without .nix> = <its value>; }.
  read =
    folder:
    let
      path = ./. + "/${folder}";
      files = if builtins.pathExists path then builtins.readDir path else { };
      names = builtins.filter (
        name: files.${name} == "regular" && builtins.match ".*\\.nix" name != null
      ) (builtins.attrNames files);
    in
    builtins.listToAttrs (
      map (name: {
        name = builtins.substring 0 (builtins.stringLength name - 4) name;
        value = import (path + "/${name}");
      }) names
    );
in
{
  maintainers = read "maintainers";
  teams = read "teams";
}
