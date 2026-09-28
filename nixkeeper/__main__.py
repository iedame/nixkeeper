"""One sync: nixpkgs index + package lists -> tracked packages -> Repology ->
rows -> GitHub counts -> data/ -> status issue. Run from the repository root (it reads
package-lists/ and writes data/ there): `nix run .#sync`."""

from datetime import UTC, datetime

from . import history, lookup, notify, output, rows, tracking
from .sources import github
from .sources import nixpkgs as nixpkgs_source


def main():
    now = datetime.now(UTC).isoformat()
    nixpkgs = nixpkgs_source.load_index()
    wanted = tracking.tracked_packages(nixpkgs_source.read_lists(), nixpkgs)
    previous = history.load_previous_run()
    projects = lookup.collect_projects(wanted, previous)
    index_rows = rows.build_rows(projects, nixpkgs)
    rows.add_source_links(index_rows, nixpkgs, nixpkgs_source.channel_revision())
    history.add_outdated_since(index_rows, previous, now)
    github.add_counts(index_rows)
    output.write(projects, {"checkedAt": now, "packages": index_rows})
    notify.notify(previous, index_rows, now)


if __name__ == "__main__":
    main()
