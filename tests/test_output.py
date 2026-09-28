import json
import os
import tempfile
import unittest

from nixkeeper.output import data_file, write
from tests.helpers import project


class Output(unittest.TestCase):
    def test_data_file_is_safe(self):
        self.assertEqual(data_file("python:requests"), "python_requests.json")
        self.assertEqual(data_file("wesnoth"), "wesnoth.json")
        self.assertEqual(data_file("a/b c"), "a_b_c.json")

    def test_write_replaces_the_whole_folder(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "data")
            os.makedirs(out)
            with open(os.path.join(out, "removed-package.json"), "w") as f:
                f.write("[]")
            os.makedirs(out + ".tmp")  # leftover from a failed run
            write({"wesnoth": project("wesnoth", ["wesnoth"], [{"repo": "x"}], "wesnoth")},
                  {"checkedAt": "now", "packages": []}, out)
            self.assertEqual(sorted(os.listdir(out)), ["index.json", "wesnoth.json"])
            self.assertFalse(os.path.exists(out + ".tmp"))
            with open(os.path.join(out, "wesnoth.json")) as f:
                self.assertEqual(json.load(f), [{"repo": "x"}])
