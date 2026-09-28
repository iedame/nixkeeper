# nixkeeper's own update checks, for packages where Repology can lag: a
# version only counts as newest there once repositories Repology trusts for
# that package it (the AUR alone doesn't count), so until then nixpkgs
# reads as up to date.
#
# Keyed by the package's row name (its attribute, as on the page). For each:
#   github = "owner/repo";  the repository whose tags to check
#   tags = "regex";         which tags count (Python syntax); a capture group,
#                           if there is one, is the version: "^v([0-9.]+)$"
# The highest matching version counts; if it's newer than nixpkgs', the
# package shows as outdated.
{
  wesnoth-devel = {
    github = "wesnoth/wesnoth";
    tags = "^(1\\.19\\.[0-9]+)$"; # the 1.19 development series
  };
}
