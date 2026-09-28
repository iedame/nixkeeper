"""One sync: nixpkgs index + package lists -> tracked packages -> Repology ->
rows -> Hydra builds -> GitHub counts -> data/ -> status issue. Run from the
repository root (it reads package-lists/ and writes data/ there):
`nix run .#sync`."""

from datetime import UTC, datetime

from . import history, lookup, notify, output, rows, tracking
from .sources import github, hydra
from .sources import nixpkgs as nixpkgs_source


def main():
    now = datetime.now(UTC).isoformat()
    nixpkgs = nixpkgs_source.load_index()
    wanted = tracking.tracked_packages(nixpkgs_source.read_lists(), nixpkgs)
    previous = history.load_previous_run()
    projects = lookup.collect_projects(wanted, previous)
    index_rows = rows.build_rows(projects, nixpkgs)
    revision = nixpkgs_source.channel_revision()
    rows.add_source_links(index_rows, nixpkgs, revision)
    history.add_outdated_since(index_rows, previous, now)
    in_nixpkgs = {a for row in index_rows for a in row["attrs"] if a in nixpkgs}
    broken = nixpkgs_source.broken(in_nixpkgs, revision)
    hydra.add_builds(index_rows, nixpkgs, previous, broken)
    github.add_counts(index_rows)
    output.write(projects, {"checkedAt": now, "packages": index_rows})
    notify.notify(previous, index_rows, now)


if __name__ == "__main__":
    main()
