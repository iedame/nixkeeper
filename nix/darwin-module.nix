# nixkeeper on macOS with nix-darwin (the flake's darwinModules.default): the
# daily sync and the frequent checks as launchd agents of system.primaryUser,
# on that user's own folders (as the command uses them), and optionally the
# page on this Mac with `nixkeeper serve`.
#
#   services.nixkeeper = {
#     enable = true;
#     lists.maintainers = [ "your-github-handle" ]; # or nixkeeper init's lists
#     serve.enable = true; # http://127.0.0.1:8000/
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

  # launchd starts agents with a bare PATH: where Nix (for lists in a Nix
  # folder) and gh (a token from the local login) usually are, then macOS's
  # own tools. Whole bin folders: nix-darwin passes strings on as they are.
  path = [
    "/etc/profiles/per-user/${config.system.primaryUser}/bin"
    "/run/current-system/sw/bin"
    "/nix/var/nix/profiles/default/bin"
    "/usr/bin"
    "/bin"
    "/usr/sbin"
    "/sbin"
  ];

  environment =
    common.environment cfg (toString cfg.githubTokenFile)
    // lib.optionalAttrs (cfg.dataDir != null) { NIXKEEPER_DATA_DIR = cfg.dataDir; };

  # A job's output goes to ~/Library/Logs/nixkeeper/<name>.log (Console.app
  # shows it). launchd won't create the folder, so the job does.
  agent = name: commands: {
    inherit path environment;
    script = ''
      mkdir -p "$HOME/Library/Logs/nixkeeper"
      exec >>"$HOME/Library/Logs/nixkeeper/${name}.log" 2>&1
      ${commands}
    '';
    serviceConfig.ProcessType = "Background";
  };

  run = args: "${lib.getExe cfg.package} ${args}";

  calendar = types.attrsOf types.int;
in
{
  options.services.nixkeeper = {
    enable = lib.mkEnableOption "nixkeeper, a health dashboard for the nixpkgs packages you maintain";

    inherit (common.options)
      package
      lists
      listsPath
      githubTokenFile
      notify
      githubRepo
      pageUrl
      ;

    dataDir = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "/Users/you/nixkeeper-data";
      description = "Where the data goes. Default: nixkeeper's own, ~/.local/state/nixkeeper/data.";
    };

    syncAt = mkOption {
      type = calendar;
      default = {
        Hour = 6;
        Minute = 0;
      };
      description = ''
        When the full sync runs (launchd StartCalendarInterval). A run missed
        while the Mac slept happens when it wakes.
      '';
    };

    frequentChecks = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Run the frequent update checks and the update PR check between syncs.";
      };
      at = mkOption {
        type = calendar;
        default.Minute = 23;
        description = "When they run (launchd StartCalendarInterval; by default hourly, at :23).";
      };
    };

    serve = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Keep `nixkeeper serve` running: the page on this Mac, with the data as it is.";
      };
      port = mkOption {
        type = types.port;
        default = 8000;
        description = "The port it listens on, on 127.0.0.1 only.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = common.assertions cfg;

    environment.systemPackages = [ cfg.package ];

    # The same lists (and data) for commands typed in a shell as for the jobs,
    # so `nixkeeper sync` or `nixkeeper paths` by hand agree with them.
    environment.variables =
      lib.optionalAttrs (common.listsFile cfg != null) {
        NIXKEEPER_LISTS = toString (common.listsFile cfg);
      }
      // lib.optionalAttrs (cfg.dataDir != null) { NIXKEEPER_DATA_DIR = cfg.dataDir; };

    launchd.user.agents = {
      nixkeeper-sync = lib.recursiveUpdate (agent "sync" (run "sync")) {
        serviceConfig.StartCalendarInterval = [ cfg.syncAt ];
      };

      nixkeeper-checks = lib.mkIf cfg.frequentChecks.enable (
        lib.recursiveUpdate (agent "checks" ''
          # Nothing to check against before the first sync.
          data="''${NIXKEEPER_DATA_DIR:-$HOME/.local/state/nixkeeper/data}"
          [ -e "$data/index.json" ] || exit 0
          status=0
          ${run "frequent-check"} || status=$?
          ${run "pr-check"} || status=$?
          exit $status
        '') { serviceConfig.StartCalendarInterval = [ cfg.frequentChecks.at ]; }
      );

      nixkeeper-serve = lib.mkIf cfg.serve.enable (
        lib.recursiveUpdate (agent "serve" "exec ${run "serve --port ${toString cfg.serve.port}"}") {
          serviceConfig = {
            RunAtLoad = true;
            KeepAlive = true; # restarted if it stops
          };
        }
      );
    };
  };
}
