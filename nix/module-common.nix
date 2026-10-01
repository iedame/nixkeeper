# What the NixOS and darwin modules share: the options for what to track,
# the GitHub token and notifications, and the NIXKEEPER_* variables they set.
{
  self,
  lib,
  pkgs,
}:
let
  inherit (lib) mkOption types;
  json = (pkgs.formats.json { }).type;
in
rec {
  options = {
    package = mkOption {
      type = types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "nixkeeper.packages.\${pkgs.stdenv.hostPlatform.system}.default";
      description = "The nixkeeper package to use.";
    };

    lists = mkOption {
      type = types.nullOr (
        types.submodule {
          freeformType = json;
          options = {
            maintainers = mkOption {
              type = types.listOf types.str;
              default = [ ];
              example = [ "iedame" ];
              description = "GitHub handles: every nixpkgs package listing one in meta.maintainers is tracked.";
            };
            extraPackages = mkOption {
              type = types.attrsOf (types.listOf types.str);
              default = { };
              example = {
                extra = [ "firefox" ];
              };
              description = "More packages to track, as named lists (each a filter on the page).";
            };
            updateChecks = mkOption {
              type = types.attrsOf json;
              default = { };
              description = "nixkeeper's own update checks, as in package-lists/update-checks.nix.";
            };
            ignoredUpdates = mkOption {
              type = types.attrsOf (types.attrsOf types.str);
              default = { };
              description = "nixpkgs-update attempts that don't count, as in package-lists/ignored-updates.nix.";
            };
          };
        }
      );
      default = null;
      description = "What to track, as package-lists/ has it.";
    };

    listsPath = mkOption {
      type = types.nullOr types.path;
      default = null;
      example = "/etc/nixkeeper/package-lists";
      description = ''
        Package lists elsewhere instead of `lists`: a Nix folder like
        package-lists/ (evaluated with Nix at each run) or a JSON file of what
        it evaluates to.
      '';
    };

    githubTokenFile = mkOption {
      # A path string, never copied into the (world-readable) Nix store.
      type = types.nullOr (
        types.pathWith {
          inStore = false;
          absolute = true;
        }
      );
      default = null;
      example = "/run/secrets/nixkeeper-github-token";
      description = ''
        A file holding a GitHub token: for the open PR and issue counts,
        update PRs and GitHub update checks (read only, no scopes needed), and
        the status issue if `notify` says so.
      '';
    };

    notify = mkOption {
      type = types.enum [
        "none"
        "github-issue"
      ];
      default = "none";
      description = "How to report what changed: github-issue keeps a status issue in `githubRepo` up to date.";
    };

    githubRepo = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "you/nixkeeper";
      description = "The repository for the status issue (notify = github-issue).";
    };

    pageUrl = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "https://nixkeeper.example.org/";
      description = "Where the page is, for links in notifications.";
    };
  };

  assertions = cfg: [
    {
      assertion = cfg.lists == null || cfg.listsPath == null;
      message = "services.nixkeeper: set lists or listsPath, not both.";
    }
    {
      assertion = cfg.notify != "github-issue" || (cfg.githubTokenFile != null && cfg.githubRepo != null);
      message = "services.nixkeeper.notify = \"github-issue\" needs githubTokenFile and githubRepo.";
    }
  ];

  # The lists as the jobs read them, or null for nixkeeper's own default. Set
  # in the configuration, they're a JSON file: no Nix needed to read them.
  listsFile =
    cfg:
    if cfg.lists != null then
      pkgs.writeText "nixkeeper-lists.json" (builtins.toJSON cfg.lists)
    else
      cfg.listsPath;

  # Whether reading the lists needs Nix: a folder of Nix files, not JSON.
  listsNeedNix =
    cfg:
    let
      file = listsFile cfg;
    in
    file == null || !(lib.hasSuffix ".json" (toString file));

  # The jobs' NIXKEEPER_* variables. token: where they find the token file.
  environment =
    cfg: token:
    lib.optionalAttrs (listsFile cfg != null) { NIXKEEPER_LISTS = toString (listsFile cfg); }
    // {
      NIXKEEPER_NOTIFY = cfg.notify;
    }
    // lib.optionalAttrs (cfg.githubTokenFile != null) { NIXKEEPER_GITHUB_TOKEN_FILE = token; }
    // lib.optionalAttrs (cfg.githubRepo != null) { NIXKEEPER_GITHUB_REPO = cfg.githubRepo; }
    // lib.optionalAttrs (cfg.pageUrl != null) { NIXKEEPER_PAGE_URL = cfg.pageUrl; };
}
