"""One sync: nixpkgs index + package lists -> tracked packages -> Repology ->
rows -> update checks -> meta.broken + Hydra builds -> nixpkgs-update logs ->
GitHub counts and update PRs -> data/ -> status issue. `nixkeeper sync`
(nixkeeper/cli.py); from a checkout, `nix run .#sync`."""

from datetime import UTC, datetime

from . import history, listcheck, lookup, notify, output, rows, tracking
from .changes import count_master, is_outdated
from .sources import github, hydra, nixpkgs_update, upstream
from .sources import nixpkgs as nixpkgs_source


def main():
    now = datetime.now(UTC).isoformat()
    nixpkgs = nixpkgs_source.load_index()
    lists = nixpkgs_source.read_lists()
    wanted = tracking.tracked_packages(lists, nixpkgs)
    previous = history.load_previous_run()
    projects = lookup.collect_projects(wanted, previous)
    index_rows = rows.build_rows(projects, nixpkgs)
    tracking.add_lists(index_rows, tracking.list_names(lists, nixpkgs))
    problems = listcheck.problems(lists, nixpkgs, [row["name"] for row in index_rows])
    listcheck.report(problems)
    revision = nixpkgs_source.channel_revision()
    rows.add_source_links(index_rows, nixpkgs, revision)
    upstream.add_checks(index_rows, lists.get("updateChecks") or {}, previous, now)
    in_nixpkgs = {a for row in index_rows for a in row["attrs"] if a in nixpkgs}
    broken = nixpkgs_source.broken(in_nixpkgs, revision)
    hydra.add_builds(index_rows, nixpkgs, previous, now, broken)
    # After the update checks and Hydra, before outdated-since: each can make
    # a row outdated (master, by having a newer version than the channel).
    for row in index_rows:
        count_master(row)
    history.add_outdated_since(index_rows, previous, now)
    nixpkgs_update.add_attempts(
        index_rows, nixpkgs, previous, now, lists.get("ignoredUpdates") or {}
    )
    github.add_counts(index_rows)  # and open update PRs
    outdated = [row for row in index_rows if is_outdated(row)]
    github.add_update_prs(outdated, open_prs=False)  # merged into master
    nixpkgs_update.recheck_superseded(outdated)
    index = {"checkedAt": now, "packages": index_rows}
    if problems:
        index["listProblems"] = problems
    output.write(projects, index)
    notify.notify(previous, index_rows, now)
