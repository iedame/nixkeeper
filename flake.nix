{
  description = "nixkeeper — tracks how nixpkgs unstable compares to other repos";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        inherit (pkgs) lib;
        py = pkgs.python3Packages;

        nixkeeper = py.buildPythonApplication {
          pname = "nixkeeper";
          version = "0.1.0";
          pyproject = true;
          src = lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [ ./pyproject.toml ./nixkeeper ./tests ];
          };
          build-system = [ py.setuptools ];
          dependencies = [ py.brotli ];
          # The offline tests run as part of every build.
          nativeCheckInputs = [ py.unittestCheckHook ];
          unittestFlagsArray = [ "-s" "tests" "-t" "." "-v" ];
          meta.mainProgram = "nixkeeper-sync";
        };

        listsChecker = import ./nix/package-lists.nix {
          pkgs = import nixpkgs { inherit system; config.allowAliases = false; };
        };

        sync = {
          type = "app";
          program = lib.getExe nixkeeper;
          meta.description = "Sync package data: nixpkgs + Repology + GitHub -> data/";
        };
      in {
        packages.default = nixkeeper;

        apps.sync = sync;
        apps.fetch = sync; # old name, kept as an alias
        apps.default = sync;

        checks.nixkeeper = nixkeeper; # building it runs the tests
        checks.package-lists = listsChecker.check (import ./package-lists);
        # The checker itself, against lists with known problems.
        checks.package-lists-checker =
          let
            found = map (p: p.entry) (listsChecker.problems {
              maintainers = [ "iedame" "IEDAME" "no-such-handle-nixkeeper" ];
              extraPackages = [ "opentyrian" "haskellPackages.pandoc" "python313Packages.requests"
                                "python3Packages.requests" "nosuchpkg-nixkeeper" "opentyrian" ];
            });
            expected = [ "no-such-handle-nixkeeper" "opentyrian" "python3Packages.requests" "nosuchpkg-nixkeeper" ];
          in
          assert lib.assertMsg (found == expected) "package-lists checker found ${builtins.toJSON found}";
          pkgs.runCommand "package-lists-checker-ok" { } "touch $out";

        devShells.default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (ps: [ ps.brotli ])) ];
        };
      });
}
