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
{
  wesnoth-devel = {
    github = "wesnoth/wesnoth";
    tags = "^(1\\.19\\.[0-9]+)$"; # the 1.19 development series
  };

  bbedit = {
    url = "https://www.barebones.com/support/bbedit/updates.html";
    pattern = "BBEdit ([0-9]+\\.[0-9]+\\.[0-9]+)";
  };
}
