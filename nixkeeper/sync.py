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
    config,
    datastore,
    follows,
    history,
    inferred,
    listcheck,
    lookup,
    notify,
    rows,
    scale,
    tracking,
    uptodate,
    version,
)
from .changes import count_master, is_outdated
from .sources import (
    github,
    github_bulk,
    hydra,
    hydra_digest,
    nixpkgs_update,
    updates_digest,
    upstream,
    versions_digest,
)
from .sources import nixpkgs as nixpkgs_source


def ask_hydra(attrs, nixpkgs, revision, previous, now, bulk=frozenset()):
    """Hydra's answers for attrs: (where nixpkgs marks them broken, answers
    by job), for hydra.add_builds. From nixkeeper-hydra's digest for the jobs
    it can answer (hydra_digest), and from Hydra itself for the rest that
    are due, or for all of them when the digest isn't current. bulk: attrs
    (with every package, those not on the lists) that only the digest
    answers, and whose meta.broken is the package index's (x86_64-linux),
    not evaluated. Run in the background (main)."""
    started = time.monotonic()
    deep = [a for a in attrs if a not in bulk]
    broken = nixpkgs_source.broken(deep, revision) if deep else {}
    for attr in bulk:
        if nixpkgs[attr]["meta"].get("broken"):
            broken.setdefault(attr, ["x86_64-linux"])
    found, ask = {}, []
    digest = hydra_digest.load(now)
    before = hydra.last_run(previous)[0]
    if digest is not None:
        found, ask = hydra_digest.answers(
            digest, hydra.jobs(deep, nixpkgs), broken, before
        )
    if bulk:
        found.update(
            hydra_digest.bulk_answers(
                digest, hydra.jobs(sorted(bulk), nixpkgs), broken, before
            )
        )
    due = hydra.due_jobs(deep, nixpkgs, previous, now, broken)
    jobs = ask + [j for j in due if j not in found and j not in ask]
    print(
        f"Hydra, in the background: {len(found):,} jobs from the digest, "
        f"{len(jobs)} to ask Hydra about...",
        file=sys.stderr,
    )
    fetched = {**found, **hydra.fetch(jobs, broken)}
    minutes = (time.monotonic() - started) / 60
    print(f"Hydra, in the background: done in {minutes:.0f} min", file=sys.stderr)
    return broken, fetched


def main():
    now = datetime.now(UTC).isoformat()
    nixpkgs = nixpkgs_source.load_index()
    lists = nixpkgs_source.read_lists()
    listed = tracking.tracked_packages(lists, nixpkgs)
    previous = history.load_previous_run()
    # How long it'll take (new packages cost the most); refuses past the limit.
    scale.check(lists, len(listed), history.new_packages(previous, listed))
    # With every package (the community instance), the rest of nixpkgs too:
    # read in bulk only (the digests, the listings), nothing per package.
    everything = config.all_packages()
    bulk = tracking.every_package(nixpkgs, listed) if everything else {}
    if everything:
        print(
            f"Every package: {len(listed):,} from the lists, {len(bulk):,} more "
            "read in bulk only",
            file=sys.stderr,
        )
    wanted = {**bulk, **listed}
    bulk_attrs = {a for attrs, _ in bulk.values() for a in attrs if a in nixpkgs}
    revision = nixpkgs_source.channel_revision()
    # Hydra is the slowest source (a request or more per package and
    # platform): asked from here, in the background, while the others are.
    # Each server is still asked one request at a time; only the waiting
    # overlaps. Its answers are put together with the rest further down.
    tracked = sorted({a for attrs, _ in wanted.values() for a in attrs if a in nixpkgs})
    hydra_answers = background.Background(
        ask_hydra, tracked, nixpkgs, revision, previous, now, bulk_attrs
    )
    # Repology, from nixkeeper-versions' digest first (versions_digest).
    digest = versions_digest.load(tracked, now)
    projects = lookup.collect_projects(
        wanted, previous, nixpkgs=nixpkgs, now=now, digest=digest, bulk=set(bulk)
    )
    index_rows = rows.build_rows(projects, nixpkgs)
    tracking.add_lists(index_rows, tracking.list_names(lists, nixpkgs))
    # The lists' rows (all of them, unless every package is tracked): the
    # rest are read in bulk only, and generated sets' rows are pending.
    on_lists = [row for row in index_rows if row["lists"]] if everything else index_rows
    in_bulk = (
        {row["name"] for row in index_rows if not row["lists"]} if everything else set()
    )
    if everything:
        tracking.add_pending(index_rows)
    shown = [row for row in index_rows if not row.get("pending")]

    # Repology's verdicts that are wrong for a version (up-to-date rules):
    # before the update checks and master, which can still make it outdated.
    up_to_date, up_to_date_community = community.merge_up_to_date(
        lists, [row["name"] for row in index_rows]
    )
    uptodate.apply(index_rows, up_to_date, up_to_date_community)

    problems = listcheck.problems(
        lists, nixpkgs, [row["name"] for row in index_rows], len(on_lists)
    )
    listcheck.report(problems)
    rows.add_source_links(index_rows, nixpkgs, revision)
    checks, from_community = community.merge(lists, [row["name"] for row in index_rows])
    # Checks worked out from nixpkgs' sources, for packages without a rule
    # (inferred.py): run with the rest, then compared with Repology (logged),
    # before master or follows change the rows.
    worked = inferred.work_out(lists, on_lists, checks, revision)
    to_run = worked.to_run(checks) if worked else {}
    failed = upstream.add_checks(
        index_rows, {**to_run, **checks}, previous, now, from_community, set(to_run)
    )
    if worked:
        inferred.report(worked, on_lists, checks, failed)
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
    # nixpkgs-update's attempts, from nixkeeper-updates' digest first.
    nixpkgs_update.add_attempts(
        index_rows,
        nixpkgs,
        previous,
        now,
        ignored,
        ignored_by_community,
        in_bulk,
        updates_digest.load(now),
    )
    # Open PR/issue counts and open update PRs: from one listing of all of
    # nixpkgs' open ones (github_bulk), else searched per package (the
    # lists' only). Not for pending rows: their sets are updated as a whole.
    if not github_bulk.add_counts(shown, now):
        github.add_counts(on_lists, previous, now)
    outdated = [row for row in shown if is_outdated(row)]
    # Update PRs merged into master, not in the channel yet: likewise.
    if not github_bulk.add_master_prs(outdated, revision, now):
        github.add_update_prs(
            [row for row in outdated if row["name"] not in in_bulk], open_prs=False
        )
    follows.apply_prs(index_rows, following)  # theirs are the same PRs
    nixpkgs_update.recheck_superseded(outdated)
    # version: the nixkeeper that made this data, for the page's footer.
    index = {"checkedAt": now, "packages": index_rows, "version": version()}
    if everything:
        index["allPackages"] = True
    if problems:
        index["listProblems"] = problems
    if page := listcheck.page_settings(lists):
        index["page"] = page  # the page's default theme
    datastore.write(index, datastore.kept_entries(projects, index_rows))
    # With every package, what changed for the lists' own packages only.
    notify.notify(
        {**previous, "packages": [r for r in previous["packages"] if r.get("lists")]}
        if everything
        else previous,
        on_lists,
        now,
    )
