"""GitHub: open nixpkgs PR / issue counts, via batched GraphQL searches."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

from .. import config


def token():
    """GITHUB_TOKEN (set by the workflow), else the local gh login, else None."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
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
            "User-Agent": config.USER_AGENT,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
    for err in result.get("errors") or []:
        print(f"  GitHub error: {err.get('message')}", file=sys.stderr)
    return result.get("data") or {}


def search_counts(token, queries):
    """Run several GitHub issue/PR searches in one GraphQL request and return
    their result counts, in order. A search GitHub couldn't answer gives None;
    a failed request gives all None."""
    params = ", ".join(f"$q{i}: String!" for i in range(len(queries)))
    fields = "\n".join(
        f"  s{i}: search(type: ISSUE, first: 0, query: $q{i}) {{ issueCount }}"
        for i in range(len(queries))
    )
    try:
        data = graphql(
            token,
            f"query({params}) {{\n{fields}\n}}",
            {f"q{i}": q for i, q in enumerate(queries)},
        )
    except (urllib.error.URLError, OSError, ValueError) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        print(f"  GitHub search batch failed ({e})", file=sys.stderr)
        return [None] * len(queries)
    return [(data.get(f"s{i}") or {}).get("issueCount") for i in range(len(queries))]


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


def add_counts(rows):
    """Open nixpkgs PRs and issues with each row's attribute name in the title:
    the same searches the page links to. Title-only because nixpkgs titles name
    the package, while bodies of big rebuild PRs list hundreds of unrelated ones."""
    tok = token()
    if not tok:
        print(
            "No GITHUB_TOKEN or gh login: skipping open PR/issue counts.",
            file=sys.stderr,
        )
        return
    searches = [
        (
            row,
            field,
            f"repo:{config.GITHUB_REPO} is:{kind} state:open "
            f"in:title {row['searchTerm']}",
        )
        for row in rows
        for kind, field in (("pr", "openPRs"), ("issue", "openIssues"))
    ]
    print(f"Counting open PRs/issues ({len(searches)} searches)...", file=sys.stderr)
    for start in range(0, len(searches), config.GITHUB_SEARCH_BATCH):
        batch = searches[start : start + config.GITHUB_SEARCH_BATCH]
        counts = search_counts(tok, [q for _, _, q in batch])
        for (row, field, _), count in zip(batch, counts, strict=True):
            row[field] = count
    for warning in count_warnings(rows):
        print(f"::warning::{warning}", file=sys.stderr)


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
    # searches (see permissions in .github/workflows/sync.yml).
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
            "User-Agent": config.USER_AGENT,
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return json.loads(data) if data else None


def update_status_issue(repo, token, title, body, comment=None):
    """Rewrite the open issue labelled STATUS_LABEL (opening it if there's
    none), then post comment if given. Returns the issue number."""
    try:
        api(
            "POST",
            f"/repos/{repo}/labels",
            token,
            {
                "name": STATUS_LABEL,
                "color": "5319e7",
                "description": "The issue nixkeeper keeps up to date",
            },
        )
    except urllib.error.HTTPError as e:
        if e.code != 422:  # 422: the label already exists
            raise
        e.close()
    issues = api(
        "GET",
        f"/repos/{repo}/issues?labels={STATUS_LABEL}&state=open&per_page=1",
        token,
    )
    if issues:
        number = issues[0]["number"]
        api("PATCH", f"/repos/{repo}/issues/{number}", token, {"body": body})
    else:
        number = api(
            "POST",
            f"/repos/{repo}/issues",
            token,
            {"title": title, "body": body, "labels": [STATUS_LABEL]},
        )["number"]
    if comment:
        api("POST", f"/repos/{repo}/issues/{number}/comments", token, {"body": comment})
    return number
