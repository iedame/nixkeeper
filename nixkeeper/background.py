"""Running a slow source in the background while the sync asks the others
(sync.py): each server is still asked one request at a time, as before; only
the waiting overlaps."""

import threading


class Background:
    """fn(*args), started at once in a thread of its own. result() waits for
    it and gives what it returned, or raises what it raised. The thread is a
    daemon: a sync that stops early (sys.exit) doesn't wait for it."""

    def __init__(self, fn, *args):
        self._value = self._error = None
        self._thread = threading.Thread(target=self._run, args=(fn, args), daemon=True)
        self._thread.start()

    def _run(self, fn, args):
        try:
            self._value = fn(*args)
        except BaseException as e:  # raised again in result()
            self._error = e

    def done(self):
        return not self._thread.is_alive()

    def result(self):
        self._thread.join()
        if self._error is not None:
            raise self._error
        return self._value
