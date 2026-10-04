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
# package shows as outdated (for a branch, once outdatedAfter says so).
#
# Any kind can add `frequent = true;` to also be checked by
# `nixkeeper frequent-check`, as often as you run it, not just by the daily
# sync: for packages whose new releases matter within hours, like browsers'
# security fixes.
#
# A check that found nothing newer runs every 3 days instead of daily (a
# third of them each day), unless it's frequent. It runs daily again when it
# finds a newer version, fails, its rule changes, or nixpkgs' version does.
{
  # stepmania = {
  #   github = "stepmania/stepmania";
  #   branch = "5_1-new";
  # };
}
