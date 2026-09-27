{
  description = "nixkeeper — fetches Repology status for tracked packages";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3.withPackages (ps: [ ps.brotli ]);
      in {
        apps.fetch = {
          type = "app";
          program = "${pkgs.writeShellApplication {
            name = "nixkeeper-fetch";
            runtimeInputs = [ python ];
            text = ''python3 ${./scripts/fetch.py}'';
          }}/bin/nixkeeper-fetch";
        meta.description = "Fetch Repology status for tracked packages";
        };

        devShells.default = pkgs.mkShell {
          packages = [ python ];
        };
      });
}
