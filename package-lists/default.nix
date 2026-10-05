{
  # GitHub handles; every nixpkgs package listing one of these in
  # meta.maintainers is tracked automatically (the page's "maintained" list).
  maintainers = [
    # keep-sorted start
    "iedame"
    # keep-sorted end
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
  # ┌──────────────────────────────────────────────────────────────────────┐
  # │ LOOKING FOR THIS PAGE'S UPDATE CHECKS, IGNORE AND UP-TO-DATE RULES?  │
  # │                                                                      │
  # │ They're the COMMUNITY RULES, not in this folder:                     │
  # │   community/update-checks.nix    where to look for new releases      │
  # │   community/ignored-updates.nix  bot failures that don't count       │
  # │   community/up-to-date.nix       versions Repology gets wrong        │
  # │                                                                      │
  # │ Anyone can contribute to them by pull request (docs/community.md),   │
  # │ and every nixkeeper can use them for the packages it tracks, by      │
  # │ turning them on like this:                                           │
  # └──────────────────────────────────────────────────────────────────────┘
  community = {
    updateChecks = true; # where to look for new releases
    ignoredUpdates = true; # bot failures that don't count
    upToDate = true; # versions Repology gets wrong
  };

  # Rules of this list's own, on top of the community's (and winning over
  # them for the same package). Empty here: they're all community rules.
  # See each file for the format.
  updateChecks = import ./update-checks.nix;
  ignoredUpdates = import ./ignored-updates.nix;
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
