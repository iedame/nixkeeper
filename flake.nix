{
  description = "nixkeeper — tracks how nixpkgs unstable compares to other repos";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      treefmt-nix,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
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
            fileset = lib.fileset.unions [
              ./pyproject.toml
              ./nixkeeper
              ./tests
            ];
          };
          build-system = [ py.setuptools ];
          dependencies = [ py.brotli ];
          # The offline tests run as part of every build.
          nativeCheckInputs = [ py.unittestCheckHook ];
          unittestFlagsArray = [
            "-s"
            "tests"
            "-t"
            "."
            "-v"
          ];
          meta.mainProgram = "nixkeeper-sync";
        };

        listsChecker = import ./nix/package-lists.nix {
          pkgs = import nixpkgs {
            inherit system;
            config.allowAliases = false;
          };
        };

        # `nix fmt` formats everything; checks.formatting fails on anything
        # unformatted. Settings for ruff and biome live in pyproject.toml and
        # biome.json, so running the tools directly gives the same result.
        treefmt = treefmt-nix.lib.evalModule pkgs {
          projectRootFile = "flake.nix";
          programs = {
            nixfmt.enable = true;
            ruff-format.enable = true;
            ruff-check.enable = true; # safe auto-fixes, e.g. import order
            biome = {
              enable = true;
              settings = builtins.fromJSON (builtins.readFile ./biome.json);
            };
          };
          settings.formatter.biome.includes = [
            "docs/*.js"
            "docs/*.css"
          ];
        };

        linters = with pkgs; [
          ruff
          deadnix
          statix
          actionlint
          shellcheck # used by actionlint for the workflows' run: scripts
          biome
        ];

        sync = {
          type = "app";
          program = lib.getExe nixkeeper;
          meta.description = "Sync package data: nixpkgs + Repology + GitHub -> data/";
        };
      in
      {
        packages.default = nixkeeper;

        apps = {
          inherit sync;
          fetch = sync; # old name, kept as an alias
          default = sync;
        };

        formatter = treefmt.config.build.wrapper;

        checks = {
          inherit nixkeeper; # building it runs the tests
          formatting = treefmt.config.build.check self;
          lint = pkgs.runCommand "nixkeeper-lint" { nativeBuildInputs = linters; } ''
            cd ${self}
            export HOME=$TMPDIR
            ruff check --no-cache .
            deadnix --fail .
            statix check .
            # Named explicitly: on its own actionlint looks for .git, which the
            # flake source (CI's view of the repo) doesn't include.
            actionlint .github/workflows/*.yml
            biome lint docs
            touch $out
          '';
          package-lists = listsChecker.check (import ./package-lists);
          # The checker itself, against lists with known problems.
          package-lists-checker =
            let
              found = map (p: p.entry) (
                listsChecker.problems {
                  maintainers = [
                    "iedame"
                    "IEDAME"
                    "no-such-handle-nixkeeper"
                  ];
                  extraPackages = [
                    "opentyrian"
                    "haskellPackages.pandoc"
                    "python313Packages.requests"
                    "python3Packages.requests"
                    "nosuchpkg-nixkeeper"
                    "opentyrian"
                  ];
                }
              );
              expected = [
                "no-such-handle-nixkeeper"
                "opentyrian"
                "python3Packages.requests"
                "nosuchpkg-nixkeeper"
              ];
            in
            assert lib.assertMsg (found == expected) "package-lists checker found ${builtins.toJSON found}";
            pkgs.runCommand "package-lists-checker-ok" { } "touch $out";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [ ps.brotli ]))
            treefmt.config.build.wrapper
          ]
          ++ linters;
        };
      }
    );
}
