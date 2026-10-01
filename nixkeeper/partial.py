"""Shared by the hourly checks (frequent.py, prcheck.py): each starts from the
last published data, changes a few rows, and publishes only if something
changed. Most hours nothing does, so nothing is written, committed or posted."""

import copy
import sys

from . import config, history, notify, output


def load():
    """(the last published index, a copy of its rows to change). Exits if
    there's none: the daily sync has to have run once."""
    previous = history.load_previous_run()
    if not previous["packages"]:
        sys.exit(
            f"No previous run in {config.OUT_DIR}: run the full sync first "
            "(nixkeeper sync; from a checkout, nix run .#sync)."
        )
    return previous, copy.deepcopy(previous["packages"])


def meaningful(packages):
    """packages without what changes every run anyway (when an update check
    last succeeded), to tell whether anything worth publishing changed."""
    packages = copy.deepcopy(packages)
    for row in packages:
        (row.get("upstream") or {}).pop("checkedAt", None)
    return packages


def publish(previous, packages, now, data_files=None):
    """Write packages (and data_files) and notify, if anything changed.
    checkedAt stays the daily sync's: the page's staleness warning, and every
    source these checks don't touch, go by it. Returns whether it wrote."""
    if meaningful(packages) == meaningful(previous["packages"]):
        print("Nothing changed.", file=sys.stderr)
        return False
    output.update(
        {**(data_files or {}), "index.json": {**previous, "packages": packages}}
    )
    print("Changes written.", file=sys.stderr)
    notify.notify(previous, packages, now)
    return True
