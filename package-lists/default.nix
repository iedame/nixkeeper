{
  # GitHub handles; every nixpkgs package listing one of these in
  # meta.maintainers is tracked automatically.
  maintainers = [
    "iedame"
  ];

  # Each file is a list of packages to track on top of the above: nixpkgs
  # attribute names (exactly that package) or pnames (every package with it).
  extraPackages = builtins.concatLists (map import [
    # General
    ./extra-packages.nix

    # NixOS/Gaming Team Packages
    ./gaming-team.nix

    # AArch64 Linux failures by year
    # ./aarch64-linux-2018.nix
    # ./aarch64-linux-2020.nix
    # ./aarch64-linux-2022.nix
    # ./aarch64-linux-2023.nix
    # ./aarch64-linux-2024.nix
  ]);
}
