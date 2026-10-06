"""What the daily sync's sources were, for the manifest's "sources" (the
page's "checked" panel): when each digest's data is from, and whether the
sync used it or, not trusting it, asked per package instead (and why).
Each source notes itself as it's loaded, Hydra's from the background, and
the sync takes them all once it's done."""

import threading

_noted = {}
_lock = threading.Lock()
# A reason longer than this is cut: an error's text can be long.
WHY_LENGTH = 200


def note(source, used, why=None, **about):
    """Note what source was: used (True, or False when the sync asked per
    package instead), why not, and about it (its "at" time, evaluation,
    ...). Values that are None are left out."""
    found = {"used": used, **{k: v for k, v in about.items() if v is not None}}
    if why:
        found["why"] = why if len(why) <= WHY_LENGTH else why[: WHY_LENGTH - 1] + "…"
    with _lock:
        _noted[source] = found


def taken():
    """Every source noted since the last call, {source: about}, and start
    over (a run's own only)."""
    with _lock:
        found = dict(sorted(_noted.items()))
        _noted.clear()
    return found
