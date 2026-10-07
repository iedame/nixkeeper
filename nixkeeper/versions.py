"""Comparing version strings, for the update checks and for what master has:
Repology's algorithm (libversion, https://github.com/repology/libversion,
doc/ALGORITHM.md), so nixkeeper orders versions as Repology does. The page
has the same in JavaScript (page/logic.js: compareVersions); both are
tested against Repology's test suite (tests/data/version-comparison-
tests.txt).

A version is split into numeric and alphabetic components (anything else
separates them), each ranked: pre-release (alpha, beta, rc, pre..., and
any other word) < zero < post-release (post..., patch..., pl, errata) <
nonzero < a letter suffix (1.0a: a letter right after a number, not
followed by one). Versions compare component by component, rank first,
then words by their first letter (any case), numbers as numbers; the
shorter one is padded with zeros (1 == 1.0, 1.0alpha < 1.0 < 1.0patch1 <
1.0.1 < 1.0a)."""

import functools
import re

PRE_RELEASE, ZERO, POST_RELEASE, NONZERO, LETTER_SUFFIX = range(5)
# A component: letters, or digits; and whether letters follow digits with
# nothing between them (a letter suffix's chance).
TOKEN = re.compile(r"([A-Za-z]+)|([0-9]+)")


def keyword(word):
    """A word's rank as Repology classifies it (libversion's
    classify_keyword), or None when it's no keyword."""
    w = word.lower()
    if w in ("alpha", "beta", "rc") or w.startswith("pre"):
        return PRE_RELEASE
    if w.startswith(("post", "patch")) or w in ("pl", "errata"):
        return POST_RELEASE
    return None


def components(version):
    """version's components as (rank, kind, value) tuples: kind 0 for an
    empty value (a zero), 1 for a word (its first letter, lowercase), 2 for
    a number. Trailing zeros are left out: they're what padding adds."""
    found = []
    pos = 0
    for m in TOKEN.finditer(version):
        word, number = m.groups()
        if word:
            # Right after a number, and not followed by one: a letter
            # suffix (1.0a, 1.0a.1; not 1.0a1, nor 1.0.a).
            after_number = m.start() == pos and found and found[-1][1] != 1
            followed = version[m.end() : m.end() + 1].isdigit()
            rank = keyword(word)
            if rank is None:
                rank = LETTER_SUFFIX if after_number and not followed else PRE_RELEASE
            found.append((rank, 1, word[0].lower()))
        else:
            value = int(number)
            found.append((NONZERO, 2, value) if value else (ZERO, 0, 0))
        pos = m.end()
    while found and found[-1] == (ZERO, 0, 0):
        found.pop()
    return tuple(found)


@functools.total_ordering
class Version:
    """A version as its components (components), compared as libversion
    does: component by component, the shorter one padded with zeros."""

    __slots__ = ("parts",)
    PAD = (ZERO, 0, 0)

    def __init__(self, version):
        self.parts = components(version or "")

    def _compare(self, other):
        a, b = self.parts, other.parts
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else self.PAD
            y = b[i] if i < len(b) else self.PAD
            if x != y:
                return -1 if x < y else 1
        return 0

    def __eq__(self, other):
        return isinstance(other, Version) and self.parts == other.parts

    def __lt__(self, other):
        return self._compare(other) < 0

    def __hash__(self):
        return hash(self.parts)

    def __repr__(self):
        return f"Version({self.parts!r})"


def version_key(version):
    """Sort key for version strings, ordered as Repology orders them
    (1.19.28 > 1.19.9, 1.0rc1 < 1.0 == 1 < 1.0.1)."""
    return Version(version)


def is_newer(version, than):
    """Whether version is newer than than (False if there's nothing to compare
    with)."""
    return bool(than) and version_key(version) > version_key(than)
