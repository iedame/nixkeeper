# Packages whose current version is correct, but upstream sources (like Repology)
# classify as untrusted, incorrect, or outdated.
#
# A rule here marks the package as up to date in nixkeeper, hiding the warning
# badge. Once the package updates to a newer version in nixpkgs, the rule
# becomes stale and will be reported as ready for removal.
#
# Format:
# {
#   "package-name" = "version";
# }

{
  "wesnoth-devel" = "1.19.28";
  "pacvim" = "2018-05-16";
  "steamtinkerlaunch" = "12.12-unstable-2025-07-14";
  "asc" = "2.6.3.0";
  "cataclysm-dda" = "0.I-2026-06-11-1250";
}
