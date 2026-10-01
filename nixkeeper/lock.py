"""One run at a time on a data folder: the sync and the frequent checks all
write it, and `nixkeeper page` copies it. Each holds a lock file next to the
folder (<data dir>.lock) while it runs; a second run waits for the first."""

import contextlib
import fcntl
import os
import sys

from . import config


def path(out_dir=None):
    return os.path.abspath(out_dir or config.OUT_DIR) + ".lock"


@contextlib.contextmanager
def held(out_dir=None):
    """Hold the data folder's lock, waiting (and saying so) while another run
    has it. Released when the block ends, or when the process does."""
    lock = path(out_dir)
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    with open(lock, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                f"Waiting for another nixkeeper run on {out_dir or config.OUT_DIR}...",
                file=sys.stderr,
            )
            fcntl.flock(f, fcntl.LOCK_EX)
        yield
