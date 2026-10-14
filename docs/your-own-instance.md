# A dashboard of your own

This repository is the community instance (nixkeeper.com, tracking every
nixpkgs package), and its `package-lists/` are an example: its maintainer's
packages and the NixOS gaming team's. A copy tracks only its lists. To get a
dashboard of your own (about 15 minutes, all in GitHub's web pages):

1. **Fork the repository** on GitHub, keeping "Copy the `main` branch
   only" ticked (the default): the `data` branch is all of nixpkgs' data,
   and your first sync makes your own. A fork starts with its workflows off:
   turn them on in its Actions tab.
2. **Say what to track** in `package-lists/`:
   - `default.nix`: your GitHub handle under `maintainers`, and your own
     named lists under `extraPackages` (or none);
   - `update-checks.nix`, `ignored-updates.nix` and `up-to-date.nix`: empty
     them (`{ }`) or
     replace the entries. They name this instance's packages, and
     `nix flake check` fails on entries for packages you don't track.
3. **Delete the files in `notifications/maintainers/` and
   `notifications/teams/`**: they're the community instance's subscribers,
   and each sync would open their status issues in your repository,
   mentioning them. Add your own there only if you want one issue per
   maintainer or team besides your dashboard's
   ([get notified](notifications.md)).
4. **Turn on GitHub Pages**: Settings → Pages → Source: **GitHub Actions**.
   Then Actions → "Pages: publish the page" → Run workflow (after that, it
   publishes by itself whenever the page changes). The page is then at
   `https://<you>.github.io/<repo>/`, or at your own domain if you give
   Pages one (Settings → Pages → Custom domain): the workflow writes where
   your data is into the page, so it finds it on any address. Until the
   first sync, it says it can't find the data.
5. **Run the first sync**: Actions → "Data: sync" → Run workflow (leave its
   box empty). It takes a few minutes (about 7 for 1,000 packages), creates
   the `data` branch, and opens the status issue (labelled
   `nixkeeper-status`) that the syncs keep up to date, unless the lists say
   `statusIssue = false;`. The page finds the data by itself. From then on,
   the sync workflow starts every 3 hours and syncs once a day (or every
   `NIXKEEPER_SYNC_HOURS`, a repository variable), and the hourly workflow
   looks for update PRs. Your copy reads the community instance's digests
   (Hydra's builds, Repology's versions, the update bot's attempts, the
   vulnerabilities, nixpkgs' PRs): nothing to set up for them.
6. **Optionally**, add your own [update checks](../package-lists/update-checks.nix),
   [ignore rules](../package-lists/ignored-updates.nix) and
   [up-to-date rules](../package-lists/up-to-date.nix), each documented in its
   file, or opt in to the [community rules](community.md)
   (`community = { updateChecks = true; ignoredUpdates = true; upToDate = true; };` in
   `default.nix`), pick the page's default colours (`page.theme =
   "catppuccin";`; visitors can still pick their own), and update the
   README's badges to point at your instance.
   Retake the screenshots of your own page with
   `nix run .#screenshots -- --browser google-chrome` (see
   [CONTRIBUTING.md](../CONTRIBUTING.md#screenshots) for the options).

The workflows need no secrets: they use the token GitHub gives each run, with
the permissions each workflow declares. GitHub pauses scheduled workflows in
public repositories without activity for 60 days; if the data stops
updating, re-enable the workflow in the Actions tab.

To run it somewhere other than GitHub Actions, see
[Running elsewhere](command.md).

What the lists can say is in [how it works](how-it-works.md#what-gets-tracked).
