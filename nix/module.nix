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
  common = import ./module-common.nix { inherit self lib pkgs; };

  stateDir = "/var/lib/nixkeeper";
  dataDir = "${stateDir}/data";

  # nixkeeper itself runs one job at a time on the data (data.lock).
  run = args: "${lib.getExe cfg.package} ${args}";

  service = description: script: {
    inherit description;
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    # Nix: the sync evaluates nixpkgs (meta.broken, where sources come
    # from), and reads lists in a Nix folder.
    path = [ config.nix.package ];
    environment = common.environment cfg "%d/github-token" // {
      NIXKEEPER_DATA_DIR = dataDir;
      # nix eval's cache, when the lists are a Nix folder.
      XDG_CACHE_HOME = "/var/cache/nixkeeper";
    };
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

    inherit (common.options) lists listsPath;

    syncAt = mkOption {
      type = types.str;
      default = "06:00";
      description = ''
        When the full sync runs (systemd OnCalendar). At boot, a sync also runs
        if there's no data yet or the last one is over 20 hours old.
      '';
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

    inherit (common.options)
      package
      githubTokenFile
      notify
      githubRepo
      pageUrl
      contact
      allPackages
      ;

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
    assertions = common.assertions cfg ++ [
      {
        # A system service has no home: its lists come from the configuration.
        assertion = cfg.lists != null || cfg.listsPath != null;
        message = "services.nixkeeper needs lists (or listsPath): what to track.";
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

        # At boot (and when the module is first enabled): the first sync, or
        # one missed while the machine was down. Skipped while the last sync
        # is under 20 hours old. (Persistent alone only catches up once the
        # timer has fired at least once.)
        nixkeeper-catch-up = lib.recursiveUpdate (service "nixkeeper: catch up on a missed sync" (
          run "sync --if-older 20"
        )) { wantedBy = [ "multi-user.target" ]; };

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
