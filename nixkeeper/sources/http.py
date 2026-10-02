"""GET with retries, shared by the sources that don't need more (Repology has
its own: it also falls back between domains)."""

import ipaddress
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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


def get(url, accept=None, safe=False):
    """The body of url as text, retrying after RETRY_DELAYS seconds. Returns
    None on 404; raises once every attempt has failed. safe (community
    update checks): https to public addresses only, redirects included, and
    at most MAX_BYTES; UnsafeURL is raised at once, not retried."""
    headers = {"User-Agent": config.user_agent()}
    if accept:
        headers["Accept"] = accept
    host = urllib.parse.urlsplit(url).netloc
    last_err = None
    for delay in [0, *config.RETRY_DELAYS]:
        if delay:
            print(f"  retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)
        try:
            request = urllib.request.Request(url, headers=headers)
            if safe:
                check_public(url)
            open_url = _safe_opener.open if safe else urllib.request.urlopen
            with open_url(request, timeout=20) as resp:
                if not safe:
                    return resp.read().decode(errors="replace")
                body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise UnsafeURL(f"{host} answered more than {MAX_BYTES} bytes")
                return body.decode(errors="replace")
        except urllib.error.HTTPError as e:
            e.close()  # an HTTP error is also an open response
            if e.code == 404:
                return None
            print(f"  {host} answered {e.code}", file=sys.stderr)
            last_err = e
        except UnsafeURL:
            raise
        except (urllib.error.URLError, OSError) as e:
            print(f"  {host} request failed ({e})", file=sys.stderr)
            last_err = e
    raise last_err
