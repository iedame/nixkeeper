"""Comparing version strings, for the update checks and for what master has."""

import re


def version_key(version):
    """Sort key for version strings: numeric parts compare as numbers
    (1.19.28 > 1.19.9), and a letter part sorts before a number (1.0rc1 <
    1.0.1)."""
    return tuple(
        (1, int(part), "") if part.isdigit() else (0, 0, part)
        for part in re.findall(r"\d+|[A-Za-z]+", version)
    )


def is_newer(version, than):
    """Whether version is newer than than (False if there's nothing to compare
    with)."""
    return bool(than) and version_key(version) > version_key(than)
