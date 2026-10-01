# A dashboard of your own

This repository is one instance, tracking iedame's packages and the NixOS
gaming team's. To get a dashboard of your own:

1. **Copy the repository**: "Use this template" on GitHub gives you a clean
   copy (none of this instance's history or data), or fork it (a fork starts
   with its workflows off: turn them on in its Actions tab).
2. **Say what to track** in `package-lists/`:
   - `default.nix`: your GitHub handle under `maintainers`, and your own
     named lists under `extraPackages` (or none);
   - `update-checks.nix` and `ignored-updates.nix`: empty them (`{ }`) or
     replace the entries. They name this instance's packages, and
     `nix flake check` fails on entries for packages you don't track.
3. **Turn on GitHub Pages**: Settings → Pages → Source: **GitHub Actions**.
   Then Actions → "Pages: publish the page" → Run workflow (after that, it
   publishes by itself whenever the page changes). The page is then at
   `https://<you>.github.io/<repo>/`.
4. **Run the first sync**: Actions → "Data: daily sync" → Run workflow. It
   takes a few minutes, creates the `data` branch, and opens the status issue
   (labelled `nixkeeper-status`) that the syncs keep up to date. The page
   finds the data by itself; from then on the sync runs daily at 06:00 UTC,
   and the hourly workflow looks for update PRs.
5. **Optionally**, add your own [update checks](../package-lists/update-checks.nix)
   and [ignore rules](../package-lists/ignored-updates.nix), each documented in
   its file, and update the README's badges to point at your instance.
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
