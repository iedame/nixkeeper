<!-- What this changes, and why. -->

<!--
Subscribing to a status issue (notifications/) or adding a community rule
(community/)? Only say why; the checks run by themselves, and a
subscription must be your own handle. See CONTRIBUTING.md for the rest.
-->

Kept in step, where it applies:

- [ ] `nix flake check` passes (tests, formatting, linters, package lists; CI runs it too)
- [ ] `CHANGELOG.md`, under Unreleased (a change users would notice)
- [ ] `docs/reading-the-page.md` (a new or changed status, badge, filter or column)
- [ ] `docs/data.md` (a new or changed field in the data)
- [ ] `docs/command.md` (a new or changed setting: an option or a `NIXKEEPER_*` variable)
- [ ] A community update check: `nix run .#community-check -- <attribute>` finds the version it should, and this description says where that version comes from and why
- [ ] Screenshots in `assets/screenshots/`: `nix run .#screenshots -- --browser google-chrome` (the page looks noticeably different; it retakes both the overview and the list; options in CONTRIBUTING.md, "Screenshots")
