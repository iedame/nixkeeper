"""The `nixkeeper` command: its subcommands, the old command names, and where
each setting comes from (flag, then environment, then default)."""

import io
import os
import tempfile
import unittest
from unittest import mock

from nixkeeper import cli, config


class Command(unittest.TestCase):
    def setUp(self):
        # main() sets these from the flags; put them back after each test.
        patcher = mock.patch.multiple(
            config, LISTS=config.LISTS, OUT_DIR=config.OUT_DIR, NOTIFY=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.stdout = self.patch("sys.stdout", io.StringIO())
        self.stderr = self.patch("sys.stderr", io.StringIO())

    def patch(self, target, new):
        patcher = mock.patch(target, new)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def run_command(self, *argv):
        """main(argv), with each command's main() faked: {module: mock}."""
        mains = {module: mock.Mock() for _, module in cli.COMMANDS.values()}
        modules = {module: mock.Mock(main=fake) for module, fake in mains.items()}
        with mock.patch("importlib.import_module", side_effect=modules.__getitem__):
            cli.main(list(argv))
        return mains

    def test_each_command_runs_its_module(self):
        for command, (_, module) in cli.COMMANDS.items():
            with self.subTest(command=command):
                mains = self.run_command(command)
                mains[module].assert_called_once_with()
                for other, fake in mains.items():
                    if other != module:
                        fake.assert_not_called()

    def test_flags_set_the_settings(self):
        self.run_command(
            "sync", "--lists", "my/lists.json", "--data-dir", "out", "--notify", "none"
        )
        self.assertEqual(
            (config.LISTS, config.OUT_DIR, config.NOTIFY),
            ("my/lists.json", "out", "none"),
        )

    def test_flags_before_the_command(self):
        self.run_command("--data-dir", "before", "pr-check")
        self.assertEqual(config.OUT_DIR, "before")

    def test_flag_after_the_command_wins(self):
        self.run_command("--data-dir", "before", "sync", "--data-dir", "after")
        self.assertEqual(config.OUT_DIR, "after")

    def test_flag_over_environment_over_default(self):
        os.environ["NIXKEEPER_DATA_DIR"] = "from-env"
        os.environ["NIXKEEPER_NOTIFY"] = "github-issue"
        self.run_command("sync", "--data-dir", "from-flag")
        self.assertEqual(config.OUT_DIR, "from-flag")
        self.assertEqual(config.NOTIFY, "github-issue")
        self.assertEqual(config.LISTS, config.DEFAULTS["LISTS"])

    def test_unknown_notify_method_is_refused(self):
        with self.assertRaises(SystemExit) as exit:
            self.run_command("sync", "--notify", "carrier-pigeon")
        self.assertEqual(exit.exception.code, 2)

    def test_no_command_shows_help(self):
        with self.assertRaises(SystemExit) as exit:
            cli.main([])
        self.assertEqual(exit.exception.code, 2)
        self.assertIn("sync", self.stderr.getvalue())

    def test_version(self):
        with self.assertRaises(SystemExit) as exit:
            cli.main(["--version"])
        self.assertEqual(exit.exception.code, 0)
        self.assertTrue(self.stdout.getvalue().startswith("nixkeeper "))

    def test_paths_says_where_and_why(self):
        with tempfile.TemporaryDirectory() as data:
            os.environ["NIXKEEPER_LISTS"] = "/nonexistent/lists"
            mains = self.run_command("paths", "--data-dir", data)
        out = self.stdout.getvalue()
        self.assertIn(f"{os.path.abspath(data)}  (--data-dir)", out)
        self.assertIn("/nonexistent/lists  (NIXKEEPER_LISTS, missing)", out)
        self.assertIn("none  (default)", out)
        for fake in mains.values():
            fake.assert_not_called()

    def test_old_names_still_work(self):
        for alias, command in (
            (cli.sync_alias, "sync"),
            (cli.frequent_check_alias, "frequent-check"),
            (cli.pr_check_alias, "pr-check"),
        ):
            with (
                self.subTest(command=command),
                mock.patch("sys.argv", [f"nixkeeper-{command}", "--data-dir", "x"]),
                mock.patch.object(cli, "main") as main,
            ):
                alias()
            main.assert_called_once_with([command, "--data-dir", "x"])
            self.assertIn(f"`nixkeeper {command}`", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
