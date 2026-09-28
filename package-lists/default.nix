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

    # AArch64 Linux failures by year
    # aarch64-linux-2018 = import ./aarch64-linux-2018.nix;
    # aarch64-linux-2020 = import ./aarch64-linux-2020.nix;
    # aarch64-linux-2022 = import ./aarch64-linux-2022.nix;
    # aarch64-linux-2023 = import ./aarch64-linux-2023.nix;
    # aarch64-linux-2024 = import ./aarch64-linux-2024.nix;
  };

  # Where to look for new releases of some tracked packages, on top of
  # Repology. See the file for the format.
  updateChecks = import ./update-checks.nix;
}
