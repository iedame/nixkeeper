# nixkeeper on macOS, with nix-darwin

The flake's darwin module runs the same jobs as launchd agents of your user
(`system.primaryUser`), on the same folders the command uses, so
`nixkeeper serve` or `nixkeeper paths` by hand see the same data:

```nix
{
  inputs.nixkeeper.url = "github:iedame/nixkeeper";

  outputs = { nix-darwin, nixkeeper, ... }: {
    darwinConfigurations.mac = nix-darwin.lib.darwinSystem {
      modules = [
        ./configuration.nix # your Mac's own configuration
        nixkeeper.darwinModules.default
        {
          services.nixkeeper = {
            enable = true;
            # Or leave lists out, and keep the ones `nixkeeper init` wrote in
            # ~/.config/nixkeeper/package-lists/.
            lists.maintainers = [ "your-github-handle" ];
            serve.enable = true; # the page at http://127.0.0.1:8000/
          };
        }
      ];
    };
  };
}
```

It takes the same `lists` (including `lists.community`, for the
[community rules](community.md)), `listsPath`, `githubTokenFile` (a file only you
can read; without one, a `gh` login is used for reading, as the command
does), `notify`, `githubRepo`, `pageUrl` and `contact` as the NixOS module,
and:

| Option | Default | What it sets |
|---|---|---|
| `syncAt` | `{ Hour = 6; Minute = 0; }` | when the sync runs (launchd `StartCalendarInterval`) |
| `frequentChecks.enable`, `.at` | `true`, `{ Minute = 23; }` | the frequent update checks and the update PR check, hourly |
| `serve.enable`, `.port` | `false`, `8000` | keep `nixkeeper serve` running, on 127.0.0.1 |
| `dataDir` | `~/.local/state/nixkeeper/data` | where the data goes |

The jobs' output is in `~/Library/Logs/nixkeeper/` (Console.app shows it),
each run between dated lines with the job's name and how it ended
(`── 2026-10-01 11:23:04 -03 checks finished (exit 0) ──`).
The module also installs the `nixkeeper` command, and when `lists`,
`listsPath` or `dataDir` is set, exports them to your shell
(`NIXKEEPER_LISTS`, `NIXKEEPER_DATA_DIR`, through nix-darwin's
`environment.variables`), so commands you type use the same lists and data
as the jobs. Shells nix-darwin sets up (zsh, bash, fish) get them; others,
like Nushell, need them passed on.

**The first sync** runs when the jobs are loaded, at the rebuild that adds
the module, and at every login: a catch-up job (`nixkeeper-catch-up`) syncs
if there's no data yet or the last sync is over 20 hours old. That also
makes up for a day missed while the Mac was off or logged out (launchd only
catches up on a run missed during sleep). After that, the daily sync and the
hourly checks run on their own. To sync right away, `nixkeeper sync` in a
terminal does it with the same lists and data. Or, just in case the job
didn't run, start it through launchd:

```bash
launchctl kickstart gui/$(id -u)/org.nixos.nixkeeper-sync
```

```bash
tail -f ~/Library/Logs/nixkeeper/sync.log
```

`launchctl list | grep nixkeeper` shows the jobs: the first column is a
running job's process, the second the last exit status (0: fine).

To pin a version rather than follow `main`, see
[pinning a version](command.md#pinning-a-version). When something doesn't
run: [troubleshooting](troubleshooting.md#on-macos-nix-darwin).
