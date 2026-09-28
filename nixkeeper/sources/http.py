"""GET with retries, shared by the sources that don't need more (Repology has
its own: it also falls back between domains)."""

import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import config


def get(url, accept=None):
    """The body of url as text, retrying after RETRY_DELAYS seconds. Returns
    None on 404; raises once every attempt has failed."""
    headers = {"User-Agent": config.USER_AGENT}
    if accept:
        headers["Accept"] = accept
    host = urllib.parse.urlsplit(url).netloc
    last_err = None
    for delay in [0, *config.RETRY_DELAYS]:
        if delay:
            print(f"  retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=20
            ) as resp:
                return resp.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            e.close()  # an HTTP error is also an open response
            if e.code == 404:
                return None
            print(f"  {host} answered {e.code}", file=sys.stderr)
            last_err = e
        except (urllib.error.URLError, OSError) as e:
            print(f"  {host} request failed ({e})", file=sys.stderr)
            last_err = e
    raise last_err
