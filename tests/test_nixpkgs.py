import io
import unittest
import urllib.error
from unittest import mock

from nixkeeper.sources import nixpkgs
from tests.helpers import response


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
