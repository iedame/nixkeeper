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

  # Also use the community's rules, which anyone can contribute to nixkeeper
  # (community/ in its repository), for the packages tracked here; the ones
  # above win over them.
  # community = {
  #   updateChecks = true;   # where to look for new releases
  #   ignoredUpdates = true; # bot failures that don't count
  #   upToDate = true;       # versions Repology gets wrong
  # };

  # Versions nixpkgs-update tried and failed that don't count as its failure
  # (never really released, say). See the file for the format.
  ignoredUpdates = import ./ignored-updates.nix;

  # Versions nixpkgs has that Repology gets wrong (untrusted, incorrect, or
  # compared with one that isn't really newer), counted as up to date. See
  # the file for the format.
  upToDate = import ./up-to-date.nix;

  # Packages without an update check of their own (or the community's) are
  # checked against the GitHub repository nixpkgs fetches them from, in the
  # tag scheme nixpkgs uses. To leave them to Repology alone:
  # workedOutChecks = false;

  # The page's colours for visitors who haven't picked any in its Theme menu:
  # "classic" or "catppuccin" (Latte when light, Mocha when dark).
  # page.theme = "catppuccin";

  # The most packages a sync may track (default 5000): above that the sync
  # refuses to start, so a big team or a typo can't send thousands of
  # requests by accident. Each costs about 0.3 requests to public services on
  # a typical day, 3 its first time. Raise it only to track that many on
  # purpose.
  # maxPackages = 6000;
}
