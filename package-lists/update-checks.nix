# nixkeeper's own update checks, for packages where Repology can lag: a
# version only counts as newest there once repositories Repology trusts for
# that package it (the AUR alone doesn't count), so until then nixpkgs
# reads as up to date.
#
# Keyed by the package's row name (its attribute, as on the page). Each check
# is one of:
#
#   github = "owner/repo";  a GitHub repository's tags,
#   tags = "regex";         the ones that count: "^v([0-9.]+)$"
#
#   url = "https://...";    a web page, e.g. the vendor's release notes,
#   pattern = "regex";      how a version appears on it: "Foo ([0-9.]+)"
#
# Patterns are Python regexes; a capture group, if there is one, is the
# version. The highest version found counts; if it's newer than nixpkgs', the
# package shows as outdated.
#
# Either kind can add `frequent = true;` to be checked every hour, not just in
# the daily sync (.github/workflows/quick-check.yml): for packages whose new
# releases matter within the hour, like browsers' security fixes.
{
  wesnoth-devel = {
    github = "wesnoth/wesnoth";
    tags = "^(1\\.19\\.[0-9]+)$"; # the 1.19 development series
  };

  bbedit = {
    url = "https://www.barebones.com/support/bbedit/updates.html";
    pattern = "BBEdit ([0-9]+\\.[0-9]+\\.[0-9]+)";
  };

  # Browsers: security fixes, so checked hourly. Linux stable only, which is
  # what nixpkgs follows.
  google-chrome = {
    # Google's version history API, newest first.
    url = "https://versionhistory.googleapis.com/v1/chrome/platforms/linux/channels/stable/versions";
    pattern = "\"version\": \"([0-9.]+)\"";
    frequent = true;
  };

  microsoft-edge = {
    # Microsoft's Debian repository index: where nixpkgs gets the .deb. It
    # lists every channel, so the pattern pins the stable package.
    url = "https://packages.microsoft.com/repos/edge/dists/stable/main/binary-amd64/Packages";
    pattern = "Package: microsoft-edge-stable\nVersion: ([0-9.]+)";
    frequent = true;
  };
}
