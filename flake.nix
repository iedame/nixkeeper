{
  description = "pkgwatch — fetches Repology status for tracked packages";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in {
        apps.fetch = {
          type = "app";
          program = "${pkgs.writeShellApplication {
            name = "pkgwatch-fetch";
            runtimeInputs = [ pkgs.python3 ];
            text = ''python3 ${./scripts/fetch.py}'';
          }}/bin/pkgwatch-fetch";
        };

        devShells.default = pkgs.mkShell {
          packages = [ pkgs.python3 ];
        };
      });
}
