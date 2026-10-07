import functools
import itertools
import os
import re
import unittest

from nixkeeper.versions import is_newer, version_key

# Repology's version comparison test suite
# (https://github.com/repology/version-comparison-test-suite, CC0), as of
# 2026-10-07: its plain cases ("1.0alpha" < "1.0"), not those with flags
# for options nixkeeper doesn't use (p is patch, any is patch, bounds).
SUITE = os.path.join(os.path.dirname(__file__), "data", "version-comparison-tests.txt")
CASE = re.compile(r'"(.*)" ([a-z]*)([<=>])([a-z]*) "(.*)"')


def cases():
    """(section, left, relation, right) for each plain case of the suite."""
    section = None
    with open(SUITE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                section = line
                continue
            m = CASE.fullmatch(line)
            if m and not m.group(2) and not m.group(4):
                yield section, m.group(1), m.group(3), m.group(5)


class RepologysSuite(unittest.TestCase):
    def test_every_plain_case(self):
        found = list(cases())
        self.assertGreater(len(found), 150)  # the file read as it should be
        for section, a, relation, b in found:
            with self.subTest(section=section, case=f"{a} {relation} {b}"):
                x, y = version_key(a), version_key(b)
                got = "<" if x < y else ">" if x > y else "="
                self.assertEqual(got, relation)


# libversion itself (py-libversion, nixpkgs' python3Packages.libversion):
# only where the tests run from the flake (nix flake check, nix develop),
# never needed by nixkeeper.
try:
    import libversion
except ImportError:
    libversion = None
REAL = os.path.join(os.path.dirname(__file__), "data", "real-versions.txt")


@unittest.skipUnless(libversion, "py-libversion isn't installed")
class AgainstLibversion(unittest.TestCase):
    """nixkeeper's port orders real versions as libversion does, so it can't
    drift unnoticed: the suite above covers the documented cases, this the
    shapes versions really take (nixpkgs' "unstable" rule aside, which
    libversion doesn't have)."""

    def test_real_versions_in_the_same_order(self):
        with open(REAL) as f:
            versions = [
                # "# " starts a comment; a version can start with "#" (#671).
                line.rstrip("\n")
                for line in f
                if line.strip() and not line.startswith("# ")
            ]
        self.assertGreater(len(versions), 3000)  # the file read as it should be
        # In libversion's order, each next to the one after it: agreeing on
        # every such pair, the two orders are the same.
        ordered = sorted(versions, key=functools.cmp_to_key(libversion.version_compare))
        for a, b in itertools.pairwise(ordered):
            x, y = version_key(a), version_key(b)
            ours = (x > y) - (x < y)
            if ours != libversion.version_compare(a, b):
                self.fail(
                    f"{a!r} vs {b!r}: libversion says "
                    f"{libversion.version_compare(a, b)}, nixkeeper {ours}"
                )


class Ordering(unittest.TestCase):
    def test_what_nixkeeper_relies_on(self):
        # Numbers as numbers; a release candidate before its release; a
        # trailing zero changes nothing; letter case doesn't matter.
        self.assertTrue(is_newer("1.19.28", "1.19.9"))
        self.assertTrue(is_newer("1.0", "1.0rc1"))
        self.assertTrue(is_newer("2.0.0", "2.0.0-beta.1"))
        self.assertFalse(is_newer("1.0", "1"))
        self.assertEqual(version_key("1.0RC1"), version_key("1.0rc1"))
        # MELPA's dates and Typst's semver, as the version sources use them.
        self.assertTrue(is_newer("20251005.508", "20250820.1200"))
        self.assertTrue(is_newer("0.10.0", "0.9.2"))

    def test_nixpkgs_unstable_is_after_its_version(self):
        # nixpkgs' snapshots after a release, and of packages without any.
        self.assertTrue(is_newer("1.2-unstable-2025-05-01", "1.2"))
        self.assertTrue(is_newer("1.3", "1.2-unstable-2025-05-01"))
        self.assertTrue(is_newer("0.37-unstable-2026-06-03", "0.37"))
        self.assertTrue(is_newer("0.3.21-unstable-2025-08-15-6.6.158", "0.3.21"))
        self.assertTrue(is_newer("0-unstable-2022-07-13", "0"))
        self.assertTrue(is_newer("0-unstable-2026-09-01", "0-unstable-2026-08-22"))
        # A release candidate stays before its release.
        self.assertTrue(is_newer("1.2", "1.2rc1-unstable-2025-01-01"))
        # Before any release, whichever way it's written: the first release
        # is newer (not "unstable" against 0.0.1's second 0).
        self.assertTrue(is_newer("0.0.1", "0-unstable-2023-04-26"))
        self.assertTrue(is_newer("0.0.1", "unstable-2023-04-26"))
        self.assertEqual(
            version_key("unstable-2023-04-26"), version_key("0-unstable-2023-04-26")
        )

    def test_a_key_for_max_sets_and_tuples(self):
        versions = ["1.0", "1.0.1", "1.0rc1", "1"]
        self.assertEqual(max(versions, key=version_key), "1.0.1")
        self.assertEqual(len({version_key("1"), version_key("1.0")}), 1)
        self.assertLess((version_key("1.0"), False), (version_key("1.0"), True))

    def test_nothing_to_compare(self):
        self.assertFalse(is_newer("1.0", None))
        self.assertFalse(is_newer("1.0", ""))
        # No version isn't a newer one, though Repology's order puts it (as 0)
        # above an unstable version: master missing isn't master ahead.
        self.assertFalse(is_newer("", "0-unstable-2022-07-13"))
        self.assertFalse(is_newer(None, "0-unstable-2022-07-13"))
        self.assertEqual(version_key(""), version_key("0"))
