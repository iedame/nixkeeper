"""Sample data and fakes shared by the tests."""
import io
import json
import urllib.error
from unittest import mock

from nixkeeper.output import data_file


def pkg(pname, platforms=None, maintainers=(), homepage=None):
    """A nixpkgs index entry, trimmed to the fields nixkeeper reads."""
    meta = {"maintainers": [{"github": m} for m in maintainers]}
    if platforms is not None:
        meta["platforms"] = platforms
    if homepage is not None:
        meta["homepage"] = homepage
    return {"pname": pname, "meta": meta}


def nix(srcname, version, status):
    """A Repology entry for nix_unstable."""
    return {"repo": "nix_unstable", "srcname": srcname, "version": version, "status": status}


def other(repo, version, status):
    """A Repology entry for some other repo."""
    return {"repo": repo, "srcname": "x", "version": version, "status": status}


def project(name, attrs, entries, project_name=None, **extra):
    """A lookup.collect_projects() result entry."""
    key = project_name or name
    return {"name": name, "project": project_name, "attrs": attrs, "entries": entries,
            "dataFile": data_file(key), **extra}


def response(body, url="https://repology.org/api/v1/project/x"):
    """A fake urlopen() response returning body as JSON."""
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = json.dumps(body).encode()
    resp.geturl.return_value = url
    return resp


def http_error(code):
    # With a body of its own, HTTPError doesn't create a temporary file (which
    # would show up as a ResourceWarning).
    return urllib.error.HTTPError("https://example.org", code, "err", {}, io.BytesIO())


LINUX = ["x86_64-linux", "aarch64-linux"]
DARWIN = ["aarch64-darwin"]

NIXPKGS = {
    "wesnoth": pkg("wesnoth", LINUX + DARWIN, ["iedame"], "https://www.wesnoth.org/"),
    "wesnoth-devel": pkg("wesnoth-devel", LINUX + DARWIN, ["IEDAME"]),
    "heroic": pkg("heroic", LINUX, ["iedame"], ["https://heroic.example", "https://mirror.example"]),
    "heroic-unwrapped": pkg("heroic-unwrapped", LINUX, ["iedame"]),
    "typstPackages.heroic": pkg("heroic", LINUX),
    "_1password-gui": pkg("1password", LINUX + DARWIN),
    "_1password-gui-beta": pkg("1password", LINUX + DARWIN),
    "bbedit": pkg("bbedit", DARWIN),
    "fzssh": pkg("fzssh"),  # no platforms declared
    "lincity": pkg("lincity"),
    "pandoc": pkg("pandoc", LINUX + DARWIN),
    "haskellPackages.pandoc": pkg("pandoc", LINUX + DARWIN),
    "python313Packages.requests": pkg("requests", LINUX + DARWIN, ["iedame"]),
    "odd": pkg("odd", ["x86_64-linux", {"kernel": {"name": "darwin"}}]),
}
