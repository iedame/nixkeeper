# Security policy

## Supported versions

Only the latest release and `main` get security fixes.

## Reporting a vulnerability

Please report it privately, through
[GitHub's private vulnerability reporting](https://github.com/iedame/nixkeeper/security/advisories/new)
(the repository's Security tab → "Report a vulnerability"), not in a public
issue.

Say what's affected and how to reproduce it, if you can.

## What's in scope

- nixkeeper's code: the sync and checks (`nixkeeper/`) and the package-list
  validation (`nix/`)
- its GitHub Actions workflows: for example, anything that could misuse their
  token or write to the `data` branch unintentionally
- the page (`docs/`): for example, script injection through the data it shows

## What's not

- Vulnerabilities in a package nixkeeper tracks: report them to that project,
  or to nixpkgs through [its security process](https://github.com/NixOS/nixpkgs/security).
  nixkeeper showing a package's known CVEs is it working as intended.
- Issues in the services nixkeeper reads from (Repology, Hydra, the
  nixpkgs-update logs, GitHub): report them to those projects.

## What to expect

nixkeeper is a personal project, maintained on a best-effort basis. Expect an
acknowledgement within about a week, and a fix or an explanation after that.
There's no bug bounty. Once fixed, the report is credited in the changelog,
unless you'd rather not be named.
