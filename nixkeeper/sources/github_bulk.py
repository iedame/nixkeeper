"""nixpkgs' open pull requests and issues, listed in bulk: every one of them
in about 60 GraphQL requests (100 of each per request), however many
packages are tracked, instead of two or three searches per package
(github.py). Each package's open PR and issue counts, and its open update
PR, are then found in the list locally (Listing).

Not used for the data yet: each daily sync compares it with the searches,
in its log (compare), so the local matching can be checked against
GitHub's before the searches go."""

import re
import sys
import urllib.error

from .. import config
from . import github

QUERY = """query($owner: String!, $name: String!, $prs: String, $issues: String,
               $morePrs: Boolean!, $moreIssues: Boolean!) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: 100, after: $prs) @include(if: $morePrs) {
      pageInfo { hasNextPage endCursor }
      nodes { number title url isDraft baseRefName }
    }
    issues(states: OPEN, first: 100, after: $issues) @include(if: $moreIssues) {
      pageInfo { hasNextPage endCursor }
      nodes { number title }
    }
  }
}"""

# GitHub's title search matches whole words: a title's words are its runs
# of letters and digits, in any case ("wine" doesn't match "winetricks: ...",
# but does "... WINE_BIN ...": underscores split words too).
WORD = re.compile(r"[^\W_]+")


def words(text):
    return {w.lower() for w in WORD.findall(text or "")}


def list_open(token):
    """(open pull requests, open issues) of nixpkgs, as GraphQL nodes; raises
    if a request fails (a partial list would give wrong counts)."""
    owner, name = config.GITHUB_REPO.split("/")
    prs, issues = [], []
    cursors = {"prs": None, "issues": None}
    more = {"prs": True, "issues": True}
    while more["prs"] or more["issues"]:
        data = github.graphql(
            token,
            QUERY,
            {
                "owner": owner,
                "name": name,
                "prs": cursors["prs"],
                "issues": cursors["issues"],
                "morePrs": more["prs"],
                "moreIssues": more["issues"],
            },
        )
        repo = data.get("repository")
        if not repo:
            raise ValueError("GitHub didn't answer for the repository")
        for key, field, found in (
            ("prs", "pullRequests", prs),
            ("issues", "issues", issues),
        ):
            if not more[key]:
                continue
            page = repo.get(field)
            if page is None:
                raise ValueError(f"GitHub didn't answer for its {field}")
            found += [n for n in page["nodes"] if n]
            more[key] = page["pageInfo"]["hasNextPage"]
            cursors[key] = page["pageInfo"]["endCursor"]
    return prs, issues


class Listing:
    """Open pull requests and issues, indexed by the words in their titles
    and by the package their titles start with ("wesnoth-devel: ...")."""

    def __init__(self, prs, issues):
        self.prs, self.issues = prs, issues
        self.pr_words = self._index(prs)
        self.issue_words = self._index(issues)
        self.by_package = {}
        for pr in prs:
            package = (pr.get("title") or "").split(":", 1)[0]
            self.by_package.setdefault(package, []).append(pr)

    @staticmethod
    def _index(nodes):
        index = {}
        for i, node in enumerate(nodes):
            for word in words(node.get("title")):
                index.setdefault(word, set()).add(i)
        return index

    @staticmethod
    def _matching(index, term):
        """The nodes whose titles have every word of term."""
        found = None
        for word in words(term):
            ids = index.get(word, set())
            found = ids if found is None else found & ids
        return found or set()

    def counts(self, term):
        """(open PRs, open issues) with term's words in their titles, as
        GitHub's `in:title term` search counts them."""
        return (
            len(self._matching(self.pr_words, term)),
            len(self._matching(self.issue_words, term)),
        )

    def titles(self, term, limit=5):
        """Some matching PRs' and issues' titles, to see why counts differ."""
        prs = sorted(self._matching(self.pr_words, term))[:limit]
        issues = sorted(self._matching(self.issue_words, term))[:limit]
        return [self.prs[i]["title"] for i in prs] + [
            self.issues[i]["title"] for i in issues
        ]

    def open_update_pr(self, row):
        """The open update PR for row, as github.open_update_pr finds it among
        a search's results, here among all open PRs whose title starts with
        its name."""
        return github.open_update_pr(row, self.by_package.get(row["searchTerm"], []))


def compare(rows, now):
    """List nixpkgs' open PRs and issues, and log how the counts and update
    PRs found in them compare with the searches' (rows counted now: their
    countedAt). Changes no row; anything that fails only skips this."""
    tok = github.token()
    if not tok:
        return
    try:
        listing = Listing(*list_open(tok))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(f"Bulk PR/issue listing: skipped ({e})", file=sys.stderr)
        return
    searched = [
        r for r in rows if r.get("countedAt") == now and r.get("openPRs") is not None
    ]
    differ = []
    for row in searched:
        prs, issues = listing.counts(row["searchTerm"])
        local_pr = (listing.open_update_pr(row) or {}).get("number")
        search_pr = (row.get("openPR") or {}).get("number")
        if (prs, issues, local_pr) != (row["openPRs"], row["openIssues"], search_pr):
            differ.append((row, prs, issues, local_pr, search_pr))
    print(
        f"::group::Bulk PR/issue listing (not used yet): {len(listing.prs):,} open "
        f"PRs and {len(listing.issues):,} issues; {len(searched)} packages counted "
        f"by search today, {len(searched) - len(differ)} agree, {len(differ)} differ",
        file=sys.stderr,
    )
    for row, prs, issues, local_pr, search_pr in differ:
        print(
            f"  {row['name']} ({row['searchTerm']}): search {row['openPRs']} PRs, "
            f"{row['openIssues']} issues, update PR #{search_pr}; listing {prs}, "
            f"{issues}, #{local_pr}",
            file=sys.stderr,
        )
        for title in listing.titles(row["searchTerm"]):
            print(f"      {title}", file=sys.stderr)
    print("::endgroup::", file=sys.stderr)
