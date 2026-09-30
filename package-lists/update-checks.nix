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
#   github = "owner/repo";  for an unstable version (nixpkgs' ends in
#   branch = "name";        -unstable-YYYY-MM-DD): the commits since then on
#                           the branch it follows. Outdated once one of them
#                           has waited 90 days; to change that:
#   outdatedAfter = { days = 30; commits = 50; };
#                           whichever comes first. What's left out keeps its
#                           default (days = 90, commits off), and null turns
#                           one off: { days = null; commits = 50; }.
#
#   url = "https://...";    a web page, e.g. the vendor's release notes,
#   pattern = "regex";      how a version appears on it: "Foo ([0-9.]+)"
#
# Patterns are Python regexes; a capture group, if there is one, is the
# version. The highest version found counts; if it's newer than nixpkgs', the
# package shows as outdated (for a branch, once outdatedAfter says so).
#
# Any kind can add `frequent = true;` to be checked every hour, not just in
# the daily sync (.github/workflows/data-hourly.yml): for packages whose new
# releases matter within the hour, like browsers' security fixes.
{
  wesnoth-devel = {
    github = "wesnoth/wesnoth";
    tags = "^(1\\.19\\.[0-9]+)$"; # the 1.19 development series
  };

  # nixpkgs packages the 5.1 beta branch, unstable; Repology only knows
  # releases (the last one, 5.0.12, is from 2016), so it can't tell.
  stepmania = {
    github = "stepmania/stepmania";
    branch = "5_1-new";
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
