# Troubleshooting

How to check that nixkeeper is running as it should, wherever it runs, and
what to do when it isn't. Start with what the page says, then look where the
sync runs: [on GitHub](#on-github), [the command](#the-nixkeeper-command),
[on NixOS](#on-nixos) or [on macOS](#on-macos-nix-darwin).

## What the page tells you

- **"checked … ago"**, top right: when the last full sync ran. Up to a day
  old is normal (it runs daily). In red, with "sync may be failing", it's
  over 2 days: the sync isn't running, or keeps failing.
- **"Couldn't find the data to show"** or **"Couldn't load …/index.json"**:
  there's no data yet (no sync has run), or the page can't reach it. On
  GitHub Pages, the page reads the repository's `data` branch, so the
  repository has to be public and the sync has to have run once.
- **A pink notice above the table, "problems in the package lists"**: the
  sync found mistakes in the lists, such as a maintainer handle no nixpkgs
  package lists (a typo tracks nothing) or an update check for a package
  that isn't tracked. Fix them where the lists live; the notice goes away
  with the next sync.
- **"check failing"** on a row: that package's update check couldn't run
  (a moved page, a changed tag scheme). The row's details say why; fix the
  check in the update checks.
- **"not refreshed"**: Repology couldn't be reached for that row on the
  last run; it shows the previous data until the next sync works.

## On GitHub

The workflows run in the repository's **Actions** tab:

| Workflow | When | What to look for |
|---|---|---|
| Data: daily sync | daily, 06:00 UTC; again at 14:00 UTC, which only syncs if the last sync is over 20 hours old (GitHub skipped or delayed the morning one) and otherwise stops at once | a green run each day; it commits to the `data` branch when something changed |
| Data: hourly updates | about hourly | GitHub runs scheduled workflows on a best-effort basis: gaps of a few hours are normal |
| Pages: publish the page | when the page changes on `main`; with `CLOUDFLARE_SITE_URL` set, only by hand (skipped on pushes) | a green run after each page change, or a skipped one with your own site |
| CI: tests and lint | every push and PR | green before merging |

- **No runs at all**: GitHub pauses scheduled workflows in public
  repositories after 60 days without activity. Re-enable them in the Actions
  tab. In a fresh fork, workflows also start disabled until you enable them.
- **To run one now**: open it in the Actions tab, then **Run workflow**.
- **A failed run**: open it and read the failing step's log. A run that
  can't reach a source (Repology, Hydra, the bot's logs) keeps the previous
  data for it rather than failing.
- **A run cancelled after 20 minutes (hourly) or an hour (daily)**: that's
  its time limit, there so a run that hangs doesn't hold the data branch,
  which the other workflow waits for. A request to a site that answers too
  slowly is given up after a minute (5 for a digest's download), so a
  timeout means something else got stuck: read where the log stops. The
  next run starts afresh; nothing half-done is published.
- **The page doesn't update after a page change**: Settings → Pages →
  Source has to be **GitHub Actions**, and "Pages: publish the page" has to
  have run.
- **The status issue** (labelled `nixkeeper-status`) is rewritten by every
  sync; it lists what needs attention and comments when something newly
  does.

## The `nixkeeper` command

```bash
nixkeeper paths
```

shows where the lists and data are, which setting decided each (a flag, an
environment variable, or the default), and which are missing.

- **"No package lists at …"**: start some with
  `nixkeeper init --maintainer <your GitHub handle>`, or point `--lists`
  (or `NIXKEEPER_LISTS`) at yours.
- **"The package lists … didn't evaluate"**: Nix's error follows; it's a
  syntax or reference mistake in the lists.
- **"nixkeeper needs nix on the PATH"**: install Nix, or give the lists as
  a JSON file with `--lists`.
- **"Waiting for another nixkeeper run on …"**: another sync or check is
  writing the same data; this one continues when it's done.
- **No PR or issue counts**: there's no GitHub token. nixkeeper reads one
  from `NIXKEEPER_GITHUB_TOKEN_FILE`, else `GITHUB_TOKEN`, else the local
  `gh` login.

## On NixOS

```bash
systemctl list-timers 'nixkeeper*'
```

shows when the sync and the checks last ran and run next.

```bash
systemctl status nixkeeper-sync nixkeeper-catch-up nixkeeper-checks
```

shows each job's last result, and

```bash
journalctl -u nixkeeper-sync -u nixkeeper-catch-up -u nixkeeper-checks
```

their output, with timestamps.

- **No data after enabling the module**: the catch-up job syncs at boot and
  when the module is first switched on, if there's no data yet or the last
  sync is over 20 hours old. To sync right away:

  ```bash
  sudo systemctl start nixkeeper-sync
  ```

- **The checks job is skipped**: it waits for a first sync ("unmet
  condition" in its log).
- **The page on nginx shows no data**: the data is in
  `/var/lib/nixkeeper/data`; check that a sync has written `index.json`
  there.

## On macOS (nix-darwin)

The jobs are launchd agents of your user, and their output is in
`~/Library/Logs/nixkeeper/` (Console.app shows it too).

**1. Are the jobs loaded?**

```bash
launchctl list | grep nixkeeper
```

There should be four: `sync`, `catch-up`, `checks` and `serve` (if
`serve.enable` is on). The first column is a process ID while a job runs
(only `serve` runs all the time), `-` otherwise; the second is the last exit
status: **0 is fine**.

**2. When does a job run, and did its last run work?**

```bash
launchctl print gui/$(id -u)/org.nixos.nixkeeper-checks
```

(or `-sync`, `-catch-up`). Look for:

- `runs`: how many times it ran since it was loaded (a rebuild reloads the
  jobs and resets it);
- `last exit code`: 0 is fine; "never exited" means it hasn't run since
  it was loaded;
- `Hour` / `Minute`: its schedule, in your Mac's local time (by default the
  sync at 6:00, the checks at :23 each hour).

**3. What did it do?**

```bash
tail -20 ~/Library/Logs/nixkeeper/checks.log
```

Each run sits between dated lines with the job's name and how it ended:

```
── 2026-10-01 11:23:04 -03 checks ──
PR check: google-chrome, microsoft-edge, unciv, wesnoth-devel, xournalpp
Searching update PRs (10 searches)...
Nothing changed.
── 2026-10-01 11:23:09 -03 checks finished (exit 0) ──
```

The daily sync and the catch-up at login share `sync.log`; a catch-up that
finds recent data says "nothing to do".

**4. Is the data fresh?**

```bash
nixkeeper paths
```

shows where the data is; the page's "checked … ago" shows how old it is.
Up to a day is normal.

**5. If a job didn't run:**

- **System Settings → General → Login Items & Extensions → Allow in the
  Background**: macOS can block background jobs there. nix-darwin's agents
  show as `sh`; keep them allowed.
- **Run one now**, then read its log: `nixkeeper sync` in a terminal (it
  uses the same lists and data as the jobs), or, just in case, through
  launchd:

  ```bash
  launchctl kickstart gui/$(id -u)/org.nixos.nixkeeper-sync
  ```

  ```bash
  tail -f ~/Library/Logs/nixkeeper/sync.log
  ```

- **A missed day**: launchd only catches up on a run missed during sleep.
  If the Mac was off or logged out at 6:00, the catch-up job syncs at the
  next login.
- **Commands you type use other lists than the jobs**: open a new terminal
  after a rebuild (the module exports `NIXKEEPER_LISTS` to new shells). Then
  `nixkeeper paths` should name the same lists the jobs use.
