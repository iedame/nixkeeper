"""One sync: nixpkgs index + package lists -> tracked packages -> Repology ->
rows -> update checks -> meta.broken + Hydra builds -> nixpkgs-update logs ->
GitHub counts and update PRs -> data/ -> status issue. Hydra, the slowest,
is asked in the background from the start (background.py). `nixkeeper sync`
(nixkeeper/cli.py); from a checkout, `nix run .#sync`."""

import sys
import time
from datetime import UTC, datetime

from . import (
    background,
    community,
    follows,
    history,
    listcheck,
    lookup,
    notify,
    output,
    rows,
    scale,
    tracking,
    uptodate,
    version,
)
from .changes import count_master, is_outdated
from .sources import github, hydra, nixpkgs_update, upstream
from .sources import nixpkgs as nixpkgs_source


def ask_hydra(attrs, nixpkgs, revision, previous, now):
    """Hydra's answers for attrs: (where nixpkgs marks them broken, fetch()'s
    answers for the jobs due), for hydra.add_builds. Run in the background
    (main)."""
    started = time.monotonic()
    broken = nixpkgs_source.broken(attrs, revision)
    jobs = hydra.due_jobs(attrs, nixpkgs, previous, now, broken)
    print(f"Hydra, in the background: {len(jobs)} jobs due...", file=sys.stderr)
    fetched = hydra.fetch(jobs, broken)
    minutes = (time.monotonic() - started) / 60
    print(f"Hydra, in the background: done in {minutes:.0f} min", file=sys.stderr)
    return broken, fetched


def main():
    now = datetime.now(UTC).isoformat()
    nixpkgs = nixpkgs_source.load_index()
    lists = nixpkgs_source.read_lists()
    wanted = tracking.tracked_packages(lists, nixpkgs)
    previous = history.load_previous_run()
    # How long it'll take (new packages cost the most); refuses past the limit.
    scale.check(lists, len(wanted), history.new_packages(previous, wanted))
    revision = nixpkgs_source.channel_revision()
    # Hydra is the slowest source (a request or more per package and
    # platform): asked from here, in the background, while the others are.
    # Each server is still asked one request at a time; only the waiting
    # overlaps. Its answers are put together with the rest further down.
    tracked = sorted({a for attrs, _ in wanted.values() for a in attrs if a in nixpkgs})
    hydra_answers = background.Background(
        ask_hydra, tracked, nixpkgs, revision, previous, now
    )
    projects = lookup.collect_projects(wanted, previous, nixpkgs=nixpkgs, now=now)
    index_rows = rows.build_rows(projects, nixpkgs)
    tracking.add_lists(index_rows, tracking.list_names(lists, nixpkgs))

    # Repology's verdicts that are wrong for a version (up-to-date rules):
    # before the update checks and master, which can still make it outdated.
    up_to_date, up_to_date_community = community.merge_up_to_date(
        lists, [row["name"] for row in index_rows]
    )
    uptodate.apply(index_rows, up_to_date, up_to_date_community)

    problems = listcheck.problems(lists, nixpkgs, [row["name"] for row in index_rows])
    listcheck.report(problems)
    rows.add_source_links(index_rows, nixpkgs, revision)
    checks, from_community = community.merge(lists, [row["name"] for row in index_rows])
    upstream.add_checks(index_rows, checks, previous, now, from_community)
    if not hydra_answers.done():
        print("Waiting for Hydra's answers...", file=sys.stderr)
    broken, fetched = hydra_answers.result()
    hydra.add_builds(index_rows, nixpkgs, previous, now, broken, fetched)
    # After the update checks and Hydra, before outdated-since: each can make
    # a row outdated (master, by having a newer version than the channel).
    for row in index_rows:
        count_master(row)
    # Packages updated together with another (follows): its newest version,
    # once master is counted for it, is theirs too.
    following = follows.of(checks)
    follows.apply_versions(index_rows, following, now, from_community)
    history.add_outdated_since(index_rows, previous, now)
    ignored, ignored_by_community = community.merge_ignores(
        lists, [row["name"] for row in index_rows]
    )
    nixpkgs_update.add_attempts(
        index_rows, nixpkgs, previous, now, ignored, ignored_by_community
    )
    github.add_counts(index_rows, previous, now)  # and open update PRs
    outdated = [row for row in index_rows if is_outdated(row)]
    github.add_update_prs(outdated, open_prs=False)  # merged into master
    follows.apply_prs(index_rows, following)  # theirs are the same PRs
    nixpkgs_update.recheck_superseded(outdated)
    # version: the nixkeeper that made this data, for the page's footer.
    index = {"checkedAt": now, "packages": index_rows, "version": version()}
    if problems:
        index["listProblems"] = problems
    if page := listcheck.page_settings(lists):
        index["page"] = page  # the page's default theme
    output.write(projects, index)
    notify.notify(previous, index_rows, now)
