{
  description = "Health dashboard for the nixpkgs packages you maintain: new releases, build and update failures, and vulnerabilities, in one place.";

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
          # One version for both: bump it in pyproject.toml.
          inherit ((lib.importTOML ./pyproject.toml).project) version;
          pyproject = true;
          src = lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [
              ./LICENSE # shipped with the package (pyproject.toml: license-files)
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
          meta = {
            description = "Health dashboard for the nixpkgs packages you maintain";
            mainProgram = "nixkeeper-sync";
            license = lib.licenses.mit;
          };
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
            "tests/js/*.mjs"
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
          meta.description = "Sync data/: Repology, update checks, Hydra, nixpkgs-update logs, GitHub";
        };
        # The hourly updates (.github/workflows/data-hourly.yml), against data/.
        frequent-check = {
          type = "app";
          program = lib.getExe' nixkeeper "nixkeeper-frequent-check";
          meta.description = "Run the frequent update checks (frequent = true) against data/";
        };
        pr-check = {
          type = "app";
          program = lib.getExe' nixkeeper "nixkeeper-pr-check";
          meta.description = "Look for outdated packages' update PRs, open and merged, against data/";
        };
        # The wordmark's typeface, Oxanium (SIL Open Font License), from the
        # google/fonts commit this nixpkgs' google-fonts uses: just the one file,
        # not the whole collection.
        oxanium = pkgs.fetchurl {
          name = "oxanium.ttf";
          url = "https://raw.githubusercontent.com/google/fonts/5174b3333331c966c38f4355d50b03ca1c1df2f9/ofl/oxanium/Oxanium%5Bwght%5D.ttf";
          hash = "sha256-LOAdlG4eH/yNfuz/+9qGI77dY+r4EaIEiMS2mvRbq7A=";
        };
        # Regenerates the brand assets in assets/brand/ (scripts/brand/): the
        # mark's SVGs, the lockups with the wordmark outlined, the colour
        # tokens, the identity sheet, and the page's copies of the favicons,
        # the header's lockups and the tokens (GitHub Pages only serves docs/).
        brand = {
          type = "app";
          program = lib.getExe (
            pkgs.writeShellApplication {
              name = "nixkeeper-brand";
              runtimeInputs = [ (pkgs.python3.withPackages (ps: [ ps.uharfbuzz ])) ];
              text = ''
                [ -f flake.nix ] && [ -d assets/brand ] || {
                  echo "Run this from the repository's root." >&2
                  exit 1
                }
                python3 scripts/brand/generate.py assets/brand ${oxanium}
                python3 scripts/brand/tokens.py assets/brand
                python3 scripts/brand/identity.py assets/brand
                cp assets/brand/favicon*.svg docs/
                cp assets/brand/nixkeeper-lockup-tight*.svg docs/
                cp assets/brand/tokens.css docs/tokens.css
              '';
            }
          );
          meta.description = "Regenerate the brand assets in assets/brand/, and the page's favicon and colour tokens";
        };
        # Retakes the page's screenshots in assets/screenshots/ (scripts/screenshots.sh),
        # with the browser named by --browser: a path, or a package from this
        # nixpkgs, fetched only then.
        screenshots = {
          type = "app";
          program = lib.getExe (
            pkgs.writeShellApplication {
              name = "nixkeeper-screenshots";
              runtimeInputs = with pkgs; [
                python3
                pngquant
                imagemagick
                git
                procps
                coreutils
                gnused
              ];
              runtimeEnv.NIXPKGS = "${nixpkgs}";
              text = builtins.readFile ./scripts/screenshots.sh;
            }
          );
          meta.description = "Retake the page's screenshots in assets/screenshots/ (-- --browser <name or path>; --help for the options)";
        };
      in
      {
        packages.default = nixkeeper;

        apps = {
          inherit
            sync
            frequent-check
            pr-check
            screenshots
            brand
            ;
          fetch = sync; # old name, kept as an alias
          quick-check = frequent-check; # old name, kept as an alias
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
            shellcheck scripts/*.sh
            biome lint docs tests/js
            touch $out
          '';
          # The page's rules (docs/logic.js), with Node's own test runner.
          page = pkgs.runCommand "nixkeeper-page-tests" { nativeBuildInputs = [ pkgs.nodejs-slim ]; } ''
            cd ${self}
            node --test 'tests/js/*.test.mjs'
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
                  updateChecks = {
                    opentyrian = {
                      github = "opentyrian/opentyrian"; # listed: fine
                      tags = "^v(.+)$";
                    };
                    wesnoth = {
                      github = "wesnoth/wesnoth"; # maintained by iedame: fine
                      tags = "^(1\\.18\\.[0-9]+)$";
                    };
                    hello = {
                      github = "not a repo";
                      tag = "typo";
                    };
                    "haskellPackages.pandoc" = {
                      github = "jgm/pandoc";
                      url = "https://pandoc.org";
                    };
                    lincity = {
                      url = "ftp://example.org";
                      pattern = "([0-9.]+)";
                    };
                  };
                  ignoredUpdates = {
                    opentyrian."2.1.1" = "never released"; # fine
                    hello."1.0" = "not tracked";
                    wesnoth."1.18.9" = "";
                    lincity = { };
                  };
                }
              );
              expected = [
                "no-such-handle-nixkeeper"
                "opentyrian"
                "python3Packages.requests"
                "nosuchpkg-nixkeeper"
                "updateChecks.haskellPackages.pandoc" # both github and url
                "updateChecks.hello" # not tracked
                "updateChecks.hello" # github isn't owner/repo
                "updateChecks.hello" # no tags
                "updateChecks.hello" # unknown field "tag"
                "updateChecks.lincity" # url isn't http(s); tracked via iedame
                "ignoredUpdates.hello" # not tracked
                "ignoredUpdates.lincity" # no versions
                "ignoredUpdates.wesnoth" # empty reason
              ];
              # Named lists: on two lists is fine, twice in one isn't, and
              # "maintained" is taken.
              foundNamed = map (p: p.entry) (
                listsChecker.problems {
                  maintainers = [ "iedame" ];
                  extraPackages = {
                    extra = [ "opentyrian" ];
                    gaming-team = [
                      "opentyrian"
                      "freedink"
                      "freedink"
                    ];
                    maintained = [ ];
                  };
                }
              );
              expectedNamed = [
                "freedink"
                "extraPackages.maintained"
              ];
            in
            assert lib.assertMsg (found == expected) "package-lists checker found ${builtins.toJSON found}";
            assert lib.assertMsg (
              foundNamed == expectedNamed
            ) "package-lists checker found ${builtins.toJSON foundNamed} (named lists)";
            pkgs.runCommand "package-lists-checker-ok" { } "touch $out";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [ ps.brotli ]))
            pkgs.nodejs-slim # the page's tests (tests/js/)
            treefmt.config.build.wrapper
          ]
          ++ linters;
        };
      }
    );
}
