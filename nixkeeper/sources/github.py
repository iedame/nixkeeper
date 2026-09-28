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


def search_counts(token, queries):
    """Run several GitHub issue/PR searches in one GraphQL request and return
    their result counts, in order. A search GitHub couldn't answer gives None;
    a failed request gives all None."""
    params = ", ".join(f"$q{i}: String!" for i in range(len(queries)))
    fields = "\n".join(f"  s{i}: search(type: ISSUE, first: 0, query: $q{i}) {{ issueCount }}" for i in range(len(queries)))
    body = json.dumps({
        "query": f"query({params}) {{\n{fields}\n}}",
        "variables": {f"q{i}": q for i, q in enumerate(queries)},
    }).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "User-Agent": config.USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"  GitHub search batch failed ({e})", file=sys.stderr)
        return [None] * len(queries)
    for err in result.get("errors") or []:
        print(f"  GitHub search error: {err.get('message')}", file=sys.stderr)
    data = result.get("data") or {}
    return [(data.get(f"s{i}") or {}).get("issueCount") for i in range(len(queries))]


def add_counts(rows):
    """Open nixpkgs PRs and issues with each row's attribute name in the title:
    the same searches the page links to. Title-only because nixpkgs titles name
    the package, while bodies of big rebuild PRs list hundreds of unrelated ones."""
    tok = token()
    if not tok:
        print("No GITHUB_TOKEN or gh login: skipping open PR/issue counts.", file=sys.stderr)
        return
    searches = [
        (row, field, f"repo:{config.GITHUB_REPO} is:{kind} state:open in:title {row['searchTerm']}")
        for row in rows
        for kind, field in (("pr", "openPRs"), ("issue", "openIssues"))
    ]
    print(f"Counting open PRs/issues ({len(searches)} searches)...", file=sys.stderr)
    for start in range(0, len(searches), config.GITHUB_SEARCH_BATCH):
        batch = searches[start:start + config.GITHUB_SEARCH_BATCH]
        counts = search_counts(tok, [q for _, _, q in batch])
        for (row, field, _), count in zip(batch, counts):
            row[field] = count
