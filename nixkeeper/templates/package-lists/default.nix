# What nixkeeper tracks. `nixkeeper init` wrote this; edit it freely, then run
# `nixkeeper sync`.
{
  # GitHub handles; every nixpkgs package listing one of these in
  # meta.maintainers is tracked automatically (the page's "maintained" list).
  maintainers = [ ];

  # More packages to track, as named lists: each name becomes a filter on the
  # page (?list=<name>), so a list can be shared with the people it's for.
  # Entries are nixpkgs attribute names (exactly that package) or pnames
  # (every package with it). A package can be on several lists.
  extraPackages = {
    extra = import ./extra-packages.nix;
  };

  # Where to look for new releases of some tracked packages, on top of
  # Repology. See the file for the format.
  updateChecks = import ./update-checks.nix;

  # Also use the community update checks, rules anyone can contribute to
  # nixkeeper (community/update-checks.nix in its repository), for the
  # packages tracked here; the ones above win for the same package.
  # communityChecks = true;

  # Versions nixpkgs-update tried and failed that don't count as its failure
  # (never really released, say). See the file for the format.
  ignoredUpdates = import ./ignored-updates.nix;
}
