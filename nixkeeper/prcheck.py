"""The PR check: for every outdated package, the update PR that's open (to
review) and the one merged into master (waiting for the channel), hourly, so
those badges don't wait for the daily sync. A merged PR shows "on master" as
soon as it's merged, before Hydra has built it. Changes rarely: only when an
update PR opens, becomes ready or is merged. Run from the repository root:
`nix run .#pr-check`."""

import sys
from datetime import UTC, datetime

from . import partial
from .changes import is_outdated
from .sources import github, nixpkgs_update


def main():
    now = datetime.now(UTC).isoformat()
    previous, packages = partial.load()
    outdated = [row for row in packages if is_outdated(row)]
    if not outdated:
        print("Nothing outdated: no update PRs to look for.", file=sys.stderr)
        return
    print(f"PR check: {', '.join(row['name'] for row in outdated)}", file=sys.stderr)
    github.add_update_prs(outdated)
    # A merged PR can supersede a failed bot attempt before Hydra builds it.
    nixpkgs_update.recheck_superseded(outdated)
    partial.publish(previous, packages, now)


if __name__ == "__main__":
    main()
