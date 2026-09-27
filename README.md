nix flake check

nix eval --extra-experimental-features 'nix-command flakes' --json -f package-lists