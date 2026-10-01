{
  # GitHub handles; every nixpkgs package listing one of these in
  # meta.maintainers is tracked automatically (the page's "maintained" list).
  maintainers = [
    "iedame"
  ];

  # More packages to track, as named lists: each name becomes a filter on the
  # page (?list=<name>), so a list can be shared with the people it's for.
  # Entries are nixpkgs attribute names (exactly that package) or pnames
  # (every package with it). A package can be on several lists.
  extraPackages = {
    # General
    extra = import ./extra-packages.nix;

    # NixOS/Gaming Team Packages
    gaming-team = import ./gaming-team.nix;
  };

  # Where to look for new releases of some tracked packages, on top of
  # Repology. See the file for the format.
  updateChecks = import ./update-checks.nix;

  # Also use the community's rules, which anyone can contribute to nixkeeper
  # (community/ in its repository), for the packages tracked here; the ones
  # above win over them.
  # community = {
  #   updateChecks = true;   # where to look for new releases
  #   ignoredUpdates = true; # bot failures that don't count
  # };

  # Versions nixpkgs-update tried and failed that don't count as its failure
  # (never really released, say). See the file for the format.
  ignoredUpdates = import ./ignored-updates.nix;

  # The page's colours for visitors who haven't picked any in its Theme menu:
  # "classic" or "catppuccin" (Latte when light, Mocha when dark).
  # page.theme = "catppuccin";
}
