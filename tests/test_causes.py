"""Why things fail, across packages (causes.py)."""

import unittest

from nixkeeper import causes


def failing(name, *lines, because="compile", set_=None):
    row = {
        "name": name,
        "builds": [
            {
                "attr": name,
                "system": "x86_64-linux",
                "status": "failed",
                "failedBecause": because,
                "failedExcerpt": list(lines),
            }
        ],
    }
    if set_:
        row["set"] = set_
    return row


class ErrorLine(unittest.TestCase):
    def test_the_specific_line_not_the_generic_one(self):
        self.assertEqual(
            causes.error_line(
                [
                    "foo.c:12:3: error: call to undeclared function 'bar'",
                    "collect2: error: ld returned 1 exit status",
                ]
            ),
            "foo.c:12:3: error: call to undeclared function 'bar'",
        )
        # Only generic lines: the cause isn't in the excerpt.
        self.assertEqual(causes.error_line(["make: *** [all] Error 2"]), "")

    def test_what_differs_taken_out(self):
        a = "/build/src/a.c:12:3: error: 'x' undeclared"
        b = "/build/other/b.c:99:1: error: 'y' undeclared"
        self.assertEqual(causes.signature(a), causes.signature(b))


class Groups(unittest.TestCase):
    def test_the_same_error_grouped_titled_the_biggest_first(self):
        rows = (
            [
                failing(
                    f"py{i}", "ModuleNotFoundError: No module named 'pkg_resources'"
                )
                for i in range(4)
            ]
            + [
                failing(f"c{i}", f"/build/x{i}.c:{i}:1: error: some odd thing '{i}'")
                for i in range(3)
            ]
            + [
                failing("lone", "/build/y.c:1:1: error: unique"),
                # In a set updated in bulk: counted on its set's line, not here.
                failing(
                    "set.a",
                    "ModuleNotFoundError: No module named 'pkg_resources'",
                    set_="rPackages",
                ),
            ]
        )
        groups = causes.build_groups(rows)
        self.assertEqual([g["count"] for g in groups], [4, 3])
        first, second = groups
        self.assertEqual(first["title"], "Python module missing: pkg_resources")
        self.assertEqual(first["about"], "python")
        self.assertEqual(len(first["key"]), 10)
        self.assertNotIn("title", second)  # no known pattern: its line
        self.assertEqual(second["signature"], "<path>:N:N: error: some odd thing '…'")

    def test_one_package_counted_once(self):
        row = failing("a", "ModuleNotFoundError: No module named 'six'")
        row["builds"].append({**row["builds"][0], "system": "aarch64-linux"})
        rows = [
            row,
            failing("b", "No module named 'six'"),
            failing("c", "No module named 'six'"),
        ]
        [group] = causes.build_groups(rows)
        self.assertEqual(group["count"], 3)

    def test_the_bots_causes(self):
        rows = [
            {"name": "a", "updateFailure": True, "update": {"failedBecause": "hash"}},
            {"name": "b", "updateFailure": True, "update": {"failedBecause": "hash"}},
            {"name": "c", "updateFailure": True, "update": {}},
            {"name": "d", "updateFailure": False},
        ]
        self.assertEqual(causes.bot_causes(rows), {"hash": 2, "other": 1})


if __name__ == "__main__":
    unittest.main()
