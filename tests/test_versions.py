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

    def test_a_key_for_max_sets_and_tuples(self):
        versions = ["1.0", "1.0.1", "1.0rc1", "1"]
        self.assertEqual(max(versions, key=version_key), "1.0.1")
        self.assertEqual(len({version_key("1"), version_key("1.0")}), 1)
        self.assertLess((version_key("1.0"), False), (version_key("1.0"), True))

    def test_nothing_to_compare(self):
        self.assertFalse(is_newer("1.0", None))
        self.assertFalse(is_newer("1.0", ""))
        self.assertEqual(version_key(""), version_key("0"))
