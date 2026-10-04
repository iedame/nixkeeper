import io
import json
import subprocess
import unittest
import urllib.error
from unittest import mock

from nixkeeper.sources import nixpkgs
from tests.helpers import response


class Broken(unittest.TestCase):
    def fake_eval(self, per_system):
        """subprocess.run answering each platform's eval from per_system."""
        calls = []

        def run(cmd, **kwargs):
            system = cmd[cmd.index("--json") + 1].rsplit(".", 1)[1]
            calls.append(cmd)
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps(per_system[system])
            )

        return run, calls

    def test_broken_per_platform(self):
        run, calls = self.fake_eval(
            {
                "x86_64-linux": [False, False],
                "aarch64-linux": [False, None],  # null: didn't evaluate
                "aarch64-darwin": [True, False],
            }
        )
        with mock.patch("subprocess.run", side_effect=run):
            result = nixpkgs.broken({"wesnoth", "libfilezilla"}, "abc123")
        # Attributes go in sorted, so the answers line up with them.
        self.assertEqual(result, {"libfilezilla": ["aarch64-darwin"]})
        self.assertIn(
            "github:NixOS/nixpkgs/abc123#legacyPackages.aarch64-darwin", calls[2]
        )
        self.assertIn('["libfilezilla", "wesnoth"]', calls[0][-1])

    def test_eval_failure_is_a_warning(self):
        error = subprocess.CalledProcessError(1, "nix", stderr="…\nerror: boom\n")
        with (
            mock.patch("sys.stderr", io.StringIO()) as stderr,
            mock.patch("subprocess.run", side_effect=error),
        ):
            self.assertEqual(nixpkgs.broken({"x"}, "abc123"), {})
        self.assertIn(
            "::warning::Couldn't evaluate meta.broken on x86_64-linux: error: boom",
            stderr.getvalue(),
        )


class Sources(unittest.TestCase):
    def test_sources(self):
        answer = [{"version": "1.0", "tag": "v1.0"}, None]  # null: didn't evaluate
        done = subprocess.CompletedProcess("nix", 0, stdout=json.dumps(answer))
        with mock.patch("subprocess.run", return_value=done) as run:
            result = nixpkgs.sources({"b", "a"}, "abc123")
        self.assertEqual(result, {"a": {"version": "1.0", "tag": "v1.0"}})
        cmd = run.call_args.args[0]
        self.assertIn("github:NixOS/nixpkgs/abc123#legacyPackages.x86_64-linux", cmd)
        self.assertIn('["a", "b"]', cmd[-1])

    def test_eval_failure_raises(self):
        error = subprocess.CalledProcessError(1, "nix", stderr="…\nerror: boom\n")
        with (
            mock.patch("subprocess.run", side_effect=error),
            self.assertRaisesRegex(nixpkgs.EvalError, "^error: boom$"),
        ):
            nixpkgs.sources({"a"}, "abc123")


class ChannelRevision(unittest.TestCase):
    def test_revision(self):
        resp = response("x")
        resp.read.return_value = b"e158d9ed9b51c98974c5e66e1ba1c9e0255fecaa\n"
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(
                nixpkgs.channel_revision(), "e158d9ed9b51c98974c5e66e1ba1c9e0255fecaa"
            )

    def test_falls_back_to_the_branch(self):
        with (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch(
                "urllib.request.urlopen", side_effect=urllib.error.URLError("down")
            ),
        ):
            self.assertEqual(nixpkgs.channel_revision(), "nixos-unstable")
