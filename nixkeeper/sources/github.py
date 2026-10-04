"""GitHub: open nixpkgs PR / issue counts and the update PRs among them, via
batched GraphQL searches; the status issue; tags and branch commits for the
update checks."""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .. import config, schedule
from ..changes import is_outdated
from ..versions import is_newer, version_key


def token(use_gh=True):
    """A GitHub token, or None: from the file NIXKEEPER_GITHUB_TOKEN_FILE names
    (how a service gets its secrets, e.g. systemd credentials), else
    GITHUB_TOKEN (set by the workflows), else the local gh login unless
    use_gh is false."""
    path = os.environ.get("NIXKEEPER_GITHUB_TOKEN_FILE")
    if path:
        try:
            with open(path) as f:
                return f.read().strip() or None
        except OSError as e:
            print(
                f"::warning::couldn't read NIXKEEPER_GITHUB_TOKEN_FILE ({e})",
                file=sys.stderr,
            )
            return None
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    if not use_gh:
        return None
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        return result.stdout.strip() or None
    except FileNotFoundError:
        return None


def graphql(token, query, variables):
    """One GitHub GraphQL request. Returns its data, printing any errors
    (parts GitHub couldn't answer are then missing or null); raises if the
    request itself fails."""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "User-Agent": config.user_agent(),
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    result = _send(req, timeout=60)
    for err in result.get("errors") or []:
        print(f"  GitHub error: {err.get('message')}", file=sys.stderr)
    return result.get("data") or {}


def rate_limit_wait(err, now=None):
    """The seconds GitHub asked to wait, when err is its rate limit (403 or
    429): Retry-After (its secondary limits), or until x-ratelimit-reset once
    x-ratelimit-remaining is 0 (the hourly one). None if it's another error."""
    if not isinstance(err, urllib.error.HTTPError) or err.code not in (403, 429):
        return None
    headers = err.headers or {}
    retry_after = str(headers.get("Retry-After", "")).strip()
    if retry_after.isdigit():
        return int(retry_after)
    reset = str(headers.get("x-ratelimit-reset", "")).strip()
    if headers.get("x-ratelimit-remaining") == "0" and reset.isdigit():
        return max(0, int(reset) - int(now if now is not None else time.time()))
    return None


def _open_json(req, timeout):
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _send(req, timeout):
    """GitHub's JSON answer to req. When GitHub says to slow down (its rate
    limits), waits as long as it asks and tries once more, if that's at most
    MAX_RETRY_AFTER seconds; otherwise raises, like any failure."""
    try:
        return _open_json(req, timeout)
    except urllib.error.HTTPError as e:
        e.close()  # an HTTP error is also an open response
        wait = rate_limit_wait(e)
        if wait is None or wait > config.MAX_RETRY_AFTER:
            raise
        print(f"  GitHub asks to slow down: waiting {wait}s", file=sys.stderr)
        time.sleep(wait)
    return _open_json(req, timeout)


PR_FIELDS = "nodes { ... on PullRequest { number title url isDraft baseRefName } }"


def search_batch(token, searches):
    """Run several GitHub issue/PR searches in one GraphQL request.
    searches: [(query, first)], first being how many matching pull requests
    to return besides the count (0: just count). Returns [(count, [pull
    requests])] in order; a search GitHub couldn't answer gives (None, []), a
    failed request all of them."""
    params = ", ".join(f"$q{i}: String!" for i in range(len(searches)))
    fields = "\n".join(
        f"  s{i}: search(type: ISSUE, first: {first}, query: $q{i}) "
        f"{{ issueCount{' ' + PR_FIELDS if first else ''} }}"
        for i, (_, first) in enumerate(searches)
    )
    try:
        data = graphql(
            token,
            f"query({params}) {{\n{fields}\n}}",
            {f"q{i}": q for i, (q, _) in enumerate(searches)},
        )
    except (urllib.error.URLError, OSError, ValueError) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        print(f"  GitHub search batch failed ({e})", file=sys.stderr)
        return [(None, [])] * len(searches)
    results = []
    for i in range(len(searches)):
        found = data.get(f"s{i}") or {}
        nodes = [n for n in found.get("nodes") or [] if n and n.get("number")]
        results.append((found.get("issueCount"), nodes))
    return results


def search_counts(token, queries):
    """Result counts of several searches, in order (None where GitHub couldn't
    answer)."""
    return [count for count, _ in search_batch(token, [(q, 0) for q in queries])]


def update_prs(nodes, term):
    """The pull requests that update the package named term, by nixpkgs'
    title convention "wesnoth-devel: 1.19.24 -> 1.19.28" (exactly that
    attribute: not wesnoth-devel-extra, which search would also find)."""
    title = re.compile(rf"^{re.escape(term)}: (\S+) -> (\S+)")
    prs = []
    for node in nodes:
        if m := title.match(node.get("title") or ""):
            prs.append(
                {
                    "number": node["number"],
                    "title": node["title"],
                    "url": node["url"],
                    "draft": bool(node.get("isDraft")),
                    "base": node.get("baseRefName"),
                    "from": m.group(1),
                    "to": m.group(2),
                }
            )
    return prs


def open_update_pr(row, nodes):
    """The open PR updating row to a version newer than nixpkgs has, if any:
    the one aiming highest, a ready one before a draft."""
    prs = [
        pr
        for pr in update_prs(nodes, row["searchTerm"])
        if not row.get("nixVersion") or is_newer(pr["to"], row["nixVersion"])
    ]
    return max(prs, key=lambda p: (version_key(p["to"]), not p["draft"]), default=None)


def merged_update_pr(row, nodes):
    """The PR merged into master that updates row past nixpkgs' version (the
    channel's), if any: the one aiming highest. Only master counts: updates
    merged into staging reach master weeks later, through staging-next."""
    prs = [
        pr
        for pr in update_prs(nodes, row["searchTerm"])
        if pr["base"] == "master"
        and (not row.get("nixVersion") or is_newer(pr["to"], row["nixVersion"]))
    ]
    return max(prs, key=lambda p: version_key(p["to"]), default=None)


def latest_tags(token, repos):
    """The 100 most recent tags (by commit date) of each "owner/repo", in one
    request: {repo: [tag names]}. A repository GitHub couldn't answer is
    missing; raises if the request fails."""
    params = ", ".join(f"$o{i}: String!, $n{i}: String!" for i in range(len(repos)))
    fields = "\n".join(
        f"  r{i}: repository(owner: $o{i}, name: $n{i}) {{ refs(refPrefix: "
        '"refs/tags/", first: 100, orderBy: {field: TAG_COMMIT_DATE, '
        "direction: DESC}) { nodes { name } } }"
        for i in range(len(repos))
    )
    variables = {}
    for i, repo in enumerate(repos):
        variables[f"o{i}"], variables[f"n{i}"] = repo.split("/", 1)
    data = graphql(token, f"query({params}) {{\n{fields}\n}}", variables)
    return {
        repo: [n["name"] for n in data[f"r{i}"]["refs"]["nodes"]]
        for i, repo in enumerate(repos)
        if (data.get(f"r{i}") or {}).get("refs")
    }


def branch_commits(token, branches):
    """For each (owner/repo, branch, since, until) in branches: the branch's
    newest commit and how many commits it has since `since`, and since
    `since` up to `until` (ISO times; until may be None), in one request.
    Returns [{"oid", "committedDate", "since", "until"} or None where GitHub
    couldn't answer (no such repository or branch)], in order; raises if the
    request fails."""
    params, fields, variables = [], [], {}
    for i, (repo, branch, since, until) in enumerate(branches):
        params.append(f"$o{i}: String!, $n{i}: String!, $b{i}: String!")
        params.append(f"$s{i}: GitTimestamp!")
        counts = f"since: history(since: $s{i}) {{ totalCount }}"
        if until:
            params.append(f"$u{i}: GitTimestamp!")
            counts += f" until: history(since: $s{i}, until: $u{i}) {{ totalCount }}"
            variables[f"u{i}"] = until
        commit = f"... on Commit {{ oid committedDate {counts} }}"
        fields.append(
            f"  r{i}: repository(owner: $o{i}, name: $n{i}) "
            f"{{ ref(qualifiedName: $b{i}) {{ target {{ {commit} }} }} }}"
        )
        variables[f"o{i}"], variables[f"n{i}"] = repo.split("/", 1)
        variables[f"b{i}"] = f"refs/heads/{branch}"
        variables[f"s{i}"] = since
    data = graphql(
        token, f"query({', '.join(params)}) {{\n" + "\n".join(fields) + "\n}", variables
    )
    results = []
    for i in range(len(branches)):
        target = ((data.get(f"r{i}") or {}).get("ref") or {}).get("target") or {}
        if not target.get("committedDate"):
            results.append(None)
            continue
        results.append(
            {
                "oid": target["oid"],
                "committedDate": target["committedDate"],
                "since": (target.get("since") or {}).get("totalCount", 0),
                "until": (target.get("until") or {}).get("totalCount", 0),
            }
        )
    return results


# How many pull requests to look through for update PRs: those with the
# attribute in the title, most recently updated first.
PR_CANDIDATES = 20


def query(row, state):
    """The GitHub search for row's PRs or issues: state is "pr state:open",
    "pr is:merged" or "issue state:open". Title-only because nixpkgs titles
    name the package, while bodies of big rebuild PRs list hundreds of
    unrelated ones."""
    return (
        f"repo:{config.GITHUB_REPO} is:{state} in:title {row['searchTerm']} "
        "sort:updated-desc"
    )


def run_searches(tok, searches, handle):
    """Run searches [(row, what, query, first)] in batches, calling
    handle(row, what, count, pull requests) for each result."""
    for start in range(0, len(searches), config.GITHUB_SEARCH_BATCH):
        batch = searches[start : start + config.GITHUB_SEARCH_BATCH]
        results = search_batch(tok, [(q, first) for _, _, q, first in batch])
        for (row, what, _, _), (count, nodes) in zip(batch, results, strict=True):
            handle(row, what, count, nodes)


def quiet(row, before):
    """Whether row's counts have nothing going on: none open at the last
    sync (no PRs, no issues) and the package isn't outdated. Those are
    searched every QUIET_DAYS (schedule.due), not daily."""
    return (
        before is not None
        and before.get("openPRs") == 0
        and before.get("openIssues") == 0
        and not is_outdated(row)
    )


def add_counts(rows, previous=None, now=None):
    """Open nixpkgs PRs and issues with each row's attribute name in the title
    (the same searches the page links to), and "openPR": the open update PR
    among them, if any (their titles come with the same search). With the
    last run's data (previous) and the time (now), a package with none of
    either and nothing pending keeps them until it's due (quiet); counted
    ones are dated ("countedAt")."""
    tok = token()
    if not tok:
        print(
            "No GITHUB_TOKEN or gh login: skipping open PR/issue counts.",
            file=sys.stderr,
        )
        return
    before = {row["name"]: row for row in (previous or {}).get("packages", [])}
    searches = []
    searched = []
    for row in rows:
        old = before.get(row.get("name"))
        row.pop("openPR", None)  # found again below, if still there
        if (
            now
            and quiet(row, old)
            and not schedule.due(row["name"], old.get("countedAt"), now)
        ):
            row.update(openPRs=0, openIssues=0, countedAt=old["countedAt"])
            continue
        searched.append(row)
        searches.append((row, "openPRs", query(row, "pr state:open"), PR_CANDIDATES))
        searches.append((row, "openIssues", query(row, "issue state:open"), 0))

    def handle(row, what, count, nodes):
        row[what] = count
        if what == "openPRs" and (pr := open_update_pr(row, nodes)):
            row["openPR"] = pr

    kept = len(rows) - len(searched)
    print(
        f"Searching open PRs/issues ({len(searches)} searches"
        + (
            f"; {kept} packages with none open were counted in the last "
            f"{config.QUIET_DAYS} days)"
            if kept
            else ")"
        )
        + "...",
        file=sys.stderr,
    )
    run_searches(tok, searches, handle)
    for row in searched:
        if now and row.get("openPRs") is not None and row.get("openIssues") is not None:
            row["countedAt"] = now
    for warning in count_warnings(rows):
        print(f"::warning::{warning}", file=sys.stderr)


def add_update_prs(rows, open_prs=True):
    """The update PRs of rows (outdated ones, typically): "masterPR", the one
    merged into master that the channel doesn't have yet, and with open_prs,
    "openPR" as in add_counts (skip it when add_counts just ran). A search
    that fails leaves that field as it was."""
    tok = token()
    if not tok:
        print("No GITHUB_TOKEN or gh login: skipping update PRs.", file=sys.stderr)
        return
    searches = []
    for row in rows:
        if open_prs:
            searches.append((row, "openPR", query(row, "pr state:open"), PR_CANDIDATES))
        searches.append((row, "masterPR", query(row, "pr is:merged"), PR_CANDIDATES))

    def handle(row, what, count, nodes):
        if count is None:
            return  # the search failed: keep what the row had
        find = open_update_pr if what == "openPR" else merged_update_pr
        row.pop(what, None)
        if pr := find(row, nodes):
            row[what] = pr

    print(f"Searching update PRs ({len(searches)} searches)...", file=sys.stderr)
    run_searches(tok, searches, handle)


def count_warnings(rows):
    """Counts that are probably wrong without any error saying so. ::warning::
    lines show up as annotations on the workflow run."""
    warnings = []
    fields = ("openPRs", "openIssues")
    missing = sum(1 for row in rows for f in fields if row.get(f) is None)
    if missing:
        warnings.append(
            f"{missing} of {2 * len(rows)} open PR/issue searches failed; "
            "those counts are blank"
        )
    counted = [
        (row["openPRs"], row["openIssues"])
        for row in rows
        if row.get("openPRs") is not None and row.get("openIssues") is not None
    ]
    # A token that can't see pull requests gets issue counts back for the PR
    # searches (see permissions in .github/workflows/data-daily.yml).
    if (
        len(counted) >= 5
        and any(prs for prs, _ in counted)
        and all(prs == issues for prs, issues in counted)
    ):
        warnings.append(
            "every package's open PR count equals its open issue count: the token "
            "probably can't see pull requests (does the workflow grant "
            "pull-requests: read?)"
        )
    return warnings


STATUS_LABEL = "nixkeeper-status"


def api(method, path, token, body=None):
    """Call the GitHub REST API; returns the decoded JSON (None if empty)."""
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "User-Agent": config.user_agent(),
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return json.loads(data) if data else None


def status_issue_body(repo, token, label=STATUS_LABEL):
    """The body of the open issue labelled label, or None if there's none."""
    issues = api(
        "GET", f"/repos/{repo}/issues?labels={label}&state=open&per_page=1", token
    )
    return issues[0].get("body") or "" if issues else None


def update_status_issue(
    repo,
    token,
    title,
    body,
    comment=None,
    label=STATUS_LABEL,
    about="The issue nixkeeper keeps up to date",
):
    """Rewrite the open issue labelled label (opening it if there's none),
    then post comment if given. Returns the issue number."""
    try:
        api(
            "POST",
            f"/repos/{repo}/labels",
            token,
            {"name": label, "color": "5319e7", "description": about},
        )
    except urllib.error.HTTPError as e:
        if e.code != 422:  # 422: the label already exists
            raise
        e.close()
    issues = api(
        "GET", f"/repos/{repo}/issues?labels={label}&state=open&per_page=1", token
    )
    if issues:
        number = issues[0]["number"]
        api("PATCH", f"/repos/{repo}/issues/{number}", token, {"body": body})
    else:
        number = api(
            "POST",
            f"/repos/{repo}/issues",
            token,
            {"title": title, "body": body, "labels": [label]},
        )["number"]
    if comment:
        api("POST", f"/repos/{repo}/issues/{number}/comments", token, {"body": comment})
    return number
