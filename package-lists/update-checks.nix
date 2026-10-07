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
#   follows = "package";    updated together with that package, to the same
#                           version, by the same PRs (msedgedriver follows
#                           microsoft-edge): its newest version and update
#                           PRs count for this one too. It must be tracked
#                           as well, and can't follow another itself.
#
# Patterns are Python regexes; a capture group, if there is one, is the
# version. The highest version found counts; if it's newer than nixpkgs', the
# package shows as outdated (for a branch, once outdatedAfter says so). A
# check is the package's own source: where it and Repology disagree on
# whether nixpkgs is outdated, the check decides (Repology's verdict is shown
# beside it), so a check that finds nixpkgs' version keeps it up to date
# when one of Repology's rules lags.
#
# Any kind can add `frequent = true;` to be checked about hourly, not just in
# the daily sync (.github/workflows/data-hourly.yml): for packages whose new
# releases matter within hours, like browsers' security fixes. (GitHub may
# delay or skip scheduled runs, so expect gaps of a few hours at times.)
#
# A check that found nothing newer runs every 3 days instead of daily (a
# third of them each day), unless it's frequent. It runs daily again when it
# finds a newer version, fails, its rule changes, or nixpkgs' version does.
#
# This list's rules are all community rules (community/ in the repository,
# turned on in default.nix), so this file is empty: add a rule here only for
# something the community rules shouldn't have, or to override one.
{
  # keep-sorted start block=yes newline_separated=yes
  # keep-sorted end
}
