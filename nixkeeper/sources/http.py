"""GET with retries, shared by the sources that don't need more (Repology has
its own: it also falls back between domains)."""

import email.utils
import gzip
import ipaddress
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from .. import config

# Safe mode (community update checks): the most a page may be.
MAX_BYTES = 2_000_000


class UnsafeURL(urllib.error.URLError):
    """A URL safe mode won't fetch: not https, or not a public address."""


def check_public(url):
    """Raise UnsafeURL unless url is https and its host resolves only to
    public internet addresses (not this machine, a private network, or a
    cloud metadata service)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise UnsafeURL(f"not an https URL: {url}")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443)
    except OSError as e:
        raise urllib.error.URLError(e) from e
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise UnsafeURL(f"{parts.hostname} is at a non-public address ({address})")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to a URL check_public accepts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_safe_opener = urllib.request.build_opener(_CheckedRedirects)


def asked_wait(err, now=None):
    """The seconds a server asked to wait before trying again: the
    Retry-After of a 429 (too many requests) or 503 (unavailable) answer, in
    seconds or as a date. None if it didn't say."""
    if not isinstance(err, urllib.error.HTTPError) or err.code not in (429, 503):
        return None
    value = (err.headers or {}).get("Retry-After", "").strip()
    if value.isdigit():
        return int(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0, round((when - (now or datetime.now(UTC))).total_seconds()))


def retry_wait(planned, err, host):
    """How long to wait before retrying after err: the planned delay, or
    longer if the server asked (asked_wait). If it asked for more than
    MAX_RETRY_AFTER, raises err instead: that request fails, rather than
    stalling the whole run."""
    asked = asked_wait(err)
    if asked is None:
        return planned
    if asked > config.MAX_RETRY_AFTER:
        print(
            f"  {host} asks to wait {asked}s, longer than nixkeeper waits "
            f"({config.MAX_RETRY_AFTER}s): giving this request up",
            file=sys.stderr,
        )
        raise err
    return max(planned, asked)


def get(url, accept=None, safe=False, compressed=False):
    """The body of url as text, retrying after RETRY_DELAYS seconds. Returns
    None on 404; raises once every attempt has failed. safe (community
    update checks): https to public addresses only, redirects included, and
    at most MAX_BYTES; UnsafeURL is raised at once, not retried. compressed:
    accept a gzipped answer, for big pages from sources nixkeeper trusts (not
    with safe: MAX_BYTES couldn't hold for what it unpacks to)."""
    return _fetch(url, accept, safe, compressed)[0]


def get_bytes(url):
    """The body of url as it is (a compressed file, say), retrying as get
    does. Returns None on 404."""
    return _fetch(url, raw=True)[0]


# A page as last read: its server's tag for that version of it ("etag") and
# when it last changed ("lastModified"), as the server gave them (either can
# be missing).
NOT_MODIFIED = 304


# When each site was last asked, for pace().
_last_asked = {}
_pacing = threading.Lock()


def pace(url):
    """Wait, if need be, so url's site (its host) is asked at most once every
    SITE_PAUSE_SECONDS: update checks can have many pages on one site (PyPI,
    a vendor's), and they shouldn't arrive back to back."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    with _pacing:
        wait = _last_asked.get(host, float("-inf")) + config.SITE_PAUSE_SECONDS
        wait -= time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_asked[host] = time.monotonic()


def get_page(url, cached=None, safe=False):
    """Like get, for a page read before: cached ({"etag", "lastModified"},
    from the last time) lets the server answer that it hasn't changed since,
    without sending it again. Returns (text, cached): text None on 404, or
    NOT_MODIFIED when it hasn't changed; cached, what to send next time
    ({} if the server gives neither)."""
    pace(url)
    headers = {}
    if (cached or {}).get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if (cached or {}).get("lastModified"):
        headers["If-Modified-Since"] = cached["lastModified"]
    text, answer = _fetch(url, safe=safe, extra=headers)
    if text is NOT_MODIFIED:
        return NOT_MODIFIED, dict(cached)
    found = {
        key: answer.get(header)
        for key, header in (("etag", "ETag"), ("lastModified", "Last-Modified"))
        if answer is not None and answer.get(header)
    }
    return text, found


def _fetch(url, accept=None, safe=False, compressed=False, extra=None, raw=False):
    """get, also returning the answer's headers: (text, headers). text is
    None on 404 (headers None), or NOT_MODIFIED when the server says the page
    hasn't changed (for get_page's extra headers). raw: the body's bytes
    instead of text (get_bytes)."""
    headers = {"User-Agent": config.user_agent(), **(extra or {})}
    if accept:
        headers["Accept"] = accept
    if compressed and not safe:
        headers["Accept-Encoding"] = "gzip"
    host = urllib.parse.urlsplit(url).netloc
    last_err = None
    for attempt, delay in enumerate([0, *config.RETRY_DELAYS]):
        if attempt:
            delay = retry_wait(delay, last_err, host)
            print(f"  retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)
        try:
            request = urllib.request.Request(url, headers=headers)
            if safe:
                check_public(url)
            open_url = _safe_opener.open if safe else urllib.request.urlopen
            with open_url(request, timeout=20) as resp:
                if raw:
                    return resp.read(), resp.headers
                if not safe:
                    body = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return body.decode(errors="replace"), resp.headers
                body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise UnsafeURL(f"{host} answered more than {MAX_BYTES} bytes")
                return body.decode(errors="replace"), resp.headers
        except urllib.error.HTTPError as e:
            e.close()  # an HTTP error is also an open response
            if e.code == 404:
                return None, None
            if e.code == NOT_MODIFIED and extra:
                return NOT_MODIFIED, e.headers
            print(f"  {host} answered {e.code}", file=sys.stderr)
            last_err = e
        except UnsafeURL:
            raise
        except (urllib.error.URLError, OSError) as e:
            print(f"  {host} request failed ({e})", file=sys.stderr)
            last_err = e
    raise last_err
