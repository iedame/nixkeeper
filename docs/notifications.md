# Get notified

Any nixpkgs maintainer, or team, can get a GitHub issue of their own from
the community dashboard: rewritten by every daily sync with what needs
attention in their packages (failing, outdated, flagged vulnerable, marked
broken), and a comment when something newly does. Comments are what GitHub
notifies you about.

## Subscribe

Add a file to [`notifications/maintainers/`](../notifications/maintainers)
by pull request, named after you:

```nix
# notifications/maintainers/<your handle>.nix
{ maintainer = "<your GitHub handle>"; }
```

The daily sync then opens **nixkeeper status: @\<your handle\>** in this
repository, with the packages listing you in `meta.maintainers` (any case,
as the page's `@handle` search finds them), and mentions you in it: that
subscribes you, so its comments reach you as GitHub notifications.

For a team (its `shortName`, as in nixpkgs' `maintainers/team-list.nix`),
the file goes in [`notifications/teams/`](../notifications/teams), named
after the team (`Qt-KDE`: `qt-kde.nix`), and lists who to mention:

```nix
# notifications/teams/gaming.nix
{
  team = "Gaming";
  mention = [ "iedame" ];
}
```

Its issue, **nixkeeper status: Gaming team**, has the team's packages: those nixpkgs lists under it
(`meta.teams`), and those a list named after the team adds
([how-it-works](how-it-works.md)). A GitHub team can't be mentioned from
here (it's in another organisation), so each member is listed by handle.

Packages in the sets updated in bulk (R, Haskell, TeX Live, ...) aren't in
the issues, as they aren't in the page's counts: their set's tooling updates
them.

## You can only add yourself

Mentioning someone subscribes them, so CI checks every pull request that
changes `notifications/`: each handle a file newly mentions must be the pull
request's author, and every handle and team must be nixpkgs' (checked
against nixos-unstable itself, so a maintainer or team added this week
works) (`scripts/check-notifications.py`). To join a team's
issue, add your own handle to its `mention`; to leave, remove it (anyone
may remove). `nix flake check` also checks the files' format: the file
named after its maintainer or team, in its kind's folder. The folders and titles keep a handle and a team of the same name
apart (`maintainers/gaming.nix` and `teams/gaming.nix`; "@gaming" and
"Gaming team").

## Unsubscribe

Remove your file (or your handle from a team's `mention`). The next sync
closes an issue whose file is gone. GitHub's "Unsubscribe" button on the
issue works at once, too.

## For an instance of your own

The same folder works for any instance: the sync reads `notifications/`
beside its package lists (`NIXKEEPER_NOTIFICATIONS` to put it elsewhere),
when it notifies by issue (`NIXKEEPER_NOTIFY=github-issue`, which the
workflows set). The instance's own status issue, for everything on its
lists, is on unless the lists turn it off:

```nix
# package-lists/default.nix
statusIssue = false;
```

Turned off, the sync closes it.
