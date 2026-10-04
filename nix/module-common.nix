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
            upToDate = mkOption {
              type = types.attrsOf (types.attrsOf types.str);
              default = { };
              example = {
                pacvim = {
                  version = "2018-05-16";
                  newest = "1.1.1";
                  reason = "A snapshot from after the 1.1.1 release.";
                };
              };
              description = "Versions Repology gets wrong, counted as up to date, as in package-lists/up-to-date.nix.";
            };
            community = {
              updateChecks = mkOption {
                type = types.bool;
                default = false;
                description = ''
                  Also use the community update checks
                  (community/update-checks.nix, shipped with nixkeeper) for the
                  packages you track. Your own updateChecks win for the same
                  package.
                '';
              };
              ignoredUpdates = mkOption {
                type = types.bool;
                default = false;
                description = ''
                  Also use the community ignore rules
                  (community/ignored-updates.nix, shipped with nixkeeper) for
                  the packages you track. Your own ignoredUpdates win for the
                  same version.
                '';
              };
              upToDate = mkOption {
                type = types.bool;
                default = false;
                description = ''
                  Also use the community up-to-date rules
                  (community/up-to-date.nix, shipped with nixkeeper) for the
                  packages you track. Your own upToDate win for the same
                  package.
                '';
              };
            };
            maxPackages = mkOption {
              type = types.nullOr types.ints.positive;
              default = null;
              example = 6000;
              description = ''
                The most packages a sync may track (default 5000): above the
                limit the sync refuses to start, so a big team or a typo
                can't send thousands of requests by accident. Each costs
                about 2 requests to public services on a typical day, 6 its
                first time. Raise it only to track that many on purpose.
              '';
            };
            page.theme = mkOption {
              type = types.enum [
                "classic"
                "catppuccin"
              ];
              default = "classic";
              description = ''
                The page's colours for visitors who haven't picked any in its
                Theme menu: classic, or catppuccin (Latte when light, Mocha
                when dark). Light or dark follows each visitor's system.
              '';
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

    contact = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "you@example.org";
      description = ''
        How the people running this nixkeeper can be reached (an email or a
        URL), sent in the User-Agent to the sources it reads (Repology,
        Hydra, GitHub, ...), so their operators can get in touch. Without it,
        the User-Agent names only nixkeeper and its version.
      '';
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

  # Whether the jobs need Nix: to read lists in a folder of Nix files, or the
  # community rules (lists from listsPath may opt in to them too).
  listsNeedNix =
    cfg:
    let
      file = listsFile cfg;
    in
    file == null
    || !(lib.hasSuffix ".json" (toString file))
    || cfg.listsPath != null
    || (
      cfg.lists != null
      && (
        cfg.lists.community.updateChecks
        || cfg.lists.community.ignoredUpdates
        || cfg.lists.community.upToDate
      )
    );

  # The jobs' NIXKEEPER_* variables. token: where they find the token file.
  environment =
    cfg: token:
    lib.optionalAttrs (listsFile cfg != null) { NIXKEEPER_LISTS = toString (listsFile cfg); }
    // {
      NIXKEEPER_NOTIFY = cfg.notify;
    }
    // lib.optionalAttrs (cfg.githubTokenFile != null) { NIXKEEPER_GITHUB_TOKEN_FILE = token; }
    // lib.optionalAttrs (cfg.githubRepo != null) { NIXKEEPER_GITHUB_REPO = cfg.githubRepo; }
    // lib.optionalAttrs (cfg.pageUrl != null) { NIXKEEPER_PAGE_URL = cfg.pageUrl; }
    // lib.optionalAttrs (cfg.contact != null) { NIXKEEPER_CONTACT = cfg.contact; };
}
