# nixkeeper as a NixOS service (the flake's nixosModules.default): the daily
# sync and the frequent checks on timers, the data in /var/lib/nixkeeper, and
# optionally the page on nginx.
#
#   services.nixkeeper = {
#     enable = true;
#     lists.maintainers = [ "your-github-handle" ];
#     githubTokenFile = "/run/secrets/nixkeeper-github-token";
#     nginx.virtualHost = "nixkeeper.example.org";
#   };
self:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.nixkeeper;
  inherit (lib) mkOption types;

  stateDir = "/var/lib/nixkeeper";
  dataDir = "${stateDir}/data";

  # The lists as the sync reads them: a JSON file needs no Nix at run time.
  listsPath =
    if cfg.listsPath != null then
      cfg.listsPath
    else
      pkgs.writeText "nixkeeper-lists.json" (builtins.toJSON cfg.lists);
  listsNeedNix = cfg.listsPath != null && !(lib.hasSuffix ".json" (toString cfg.listsPath));

  # nixkeeper itself runs one job at a time on the data (data.lock).
  run = args: "${lib.getExe cfg.package} ${args}";

  service = description: script: {
    inherit description;
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    path = lib.optional listsNeedNix config.nix.package;
    environment = {
      NIXKEEPER_LISTS = toString listsPath;
      NIXKEEPER_DATA_DIR = dataDir;
      NIXKEEPER_NOTIFY = cfg.notify;
      # nix eval's cache, when the lists are a Nix folder.
      XDG_CACHE_HOME = "/var/cache/nixkeeper";
    }
    // lib.optionalAttrs (cfg.githubTokenFile != null) {
      NIXKEEPER_GITHUB_TOKEN_FILE = "%d/github-token";
    }
    // lib.optionalAttrs (cfg.githubRepo != null) { NIXKEEPER_GITHUB_REPO = cfg.githubRepo; }
    // lib.optionalAttrs (cfg.pageUrl != null) { NIXKEEPER_PAGE_URL = cfg.pageUrl; };
    serviceConfig = {
      Type = "oneshot";
      User = "nixkeeper";
      Group = "nixkeeper";
      StateDirectory = "nixkeeper";
      StateDirectoryMode = "0755"; # nginx reads the data
      CacheDirectory = "nixkeeper";
      LoadCredential = lib.optional (cfg.githubTokenFile != null) "github-token:${cfg.githubTokenFile}";
      ExecStart = script;
      # Hardening: it only reads the web and writes its own folders.
      CapabilityBoundingSet = "";
      LockPersonality = true;
      MemoryDenyWriteExecute = true;
      NoNewPrivileges = true;
      PrivateDevices = true;
      PrivateTmp = true;
      ProtectClock = true;
      ProtectControlGroups = true;
      ProtectHome = true;
      ProtectHostname = true;
      ProtectKernelLogs = true;
      ProtectKernelModules = true;
      ProtectKernelTunables = true;
      ProtectSystem = "strict";
      # AF_UNIX: the Nix daemon, when the lists are a Nix folder.
      RestrictAddressFamilies = [
        "AF_INET"
        "AF_INET6"
        "AF_UNIX"
      ];
      RestrictNamespaces = true;
      RestrictRealtime = true;
      RestrictSUIDSGID = true;
      SystemCallArchitectures = "native";
      UMask = "0022";
    };
  };
in
{
  options.services.nixkeeper = {
    enable = lib.mkEnableOption "nixkeeper, a health dashboard for the nixpkgs packages you maintain";

    package = mkOption {
      type = types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "nixkeeper.packages.\${pkgs.stdenv.hostPlatform.system}.default";
      description = "The nixkeeper package to use.";
    };

    lists = mkOption {
      type = types.submodule {
        freeformType = (pkgs.formats.json { }).type;
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
            type = types.attrsOf (pkgs.formats.json { }).type;
            default = { };
            description = "nixkeeper's own update checks, as in package-lists/update-checks.nix.";
          };
          ignoredUpdates = mkOption {
            type = types.attrsOf (types.attrsOf types.str);
            default = { };
            description = "nixpkgs-update attempts that don't count, as in package-lists/ignored-updates.nix.";
          };
        };
      };
      default = { };
      description = "What to track, as package-lists/ has it. Ignored when listsPath is set.";
    };

    listsPath = mkOption {
      type = types.nullOr types.path;
      default = null;
      example = "/etc/nixkeeper/package-lists";
      description = ''
        Package lists elsewhere instead of `lists`: a Nix folder like
        package-lists/ (evaluated with the system's Nix at each run) or a JSON
        file of what it evaluates to.
      '';
    };

    syncAt = mkOption {
      type = types.str;
      default = "06:00";
      description = "When the full sync runs (systemd OnCalendar).";
    };

    frequentChecks = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Run the frequent update checks and the update PR check between syncs.";
      };
      at = mkOption {
        type = types.str;
        default = "hourly";
        description = "When they run (systemd OnCalendar).";
      };
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
        A file holding a GitHub token, passed as a systemd credential: for the
        open PR and issue counts, update PRs and GitHub update checks (read
        only, no scopes needed), and the status issue if `notify` says so.
        Without it those are skipped.
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

    nginx.virtualHost = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "nixkeeper.example.org";
      description = ''
        Serve the page and the data on this nginx virtual host. Add TLS and
        the rest with services.nginx.virtualHosts.<name>, as for any host.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.notify != "github-issue" || (cfg.githubTokenFile != null && cfg.githubRepo != null);
        message = "services.nixkeeper.notify = \"github-issue\" needs githubTokenFile and githubRepo.";
      }
    ];

    users = {
      users.nixkeeper = {
        isSystemUser = true;
        group = "nixkeeper";
        home = stateDir;
      };
      groups.nixkeeper = { };
    };

    systemd = {
      services = {
        nixkeeper-sync = service "nixkeeper: sync the package data" (run "sync");

        nixkeeper-checks = lib.mkIf cfg.frequentChecks.enable (
          lib.recursiveUpdate
            (service "nixkeeper: frequent update checks and update PRs" (
              # Both run even if one fails; the unit fails if either did.
              pkgs.writeShellScript "nixkeeper-checks" ''
                status=0
                ${run "frequent-check"} || status=$?
                ${run "pr-check"} || status=$?
                exit $status
              ''
            ))
            {
              # Nothing to check against before the first sync.
              unitConfig.ConditionPathExists = "${dataDir}/index.json";
            }
        );
      };

      timers = {
        nixkeeper-sync = {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnCalendar = cfg.syncAt;
            Persistent = true; # a missed run (the machine was off) runs at boot
            RandomizedDelaySec = "15m";
          };
        };

        nixkeeper-checks = lib.mkIf cfg.frequentChecks.enable {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnCalendar = cfg.frequentChecks.at;
            RandomizedDelaySec = "5m";
          };
        };
      };
    };

    services.nginx = lib.mkIf (cfg.nginx.virtualHost != null) {
      enable = true;
      virtualHosts.${cfg.nginx.virtualHost} = {
        root = "${cfg.package}/share/nixkeeper/www";
        # The page finds its data as data/ next to it.
        locations."/data/".alias = "${dataDir}/";
      };
    };
  };
}
