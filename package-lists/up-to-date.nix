# Packages whose current version is correct, but upstream sources (like Repology)
# classify as untrusted, incorrect, or outdated.
#
# A rule here marks the package as up to date in nixkeeper, hiding the warning
# badge. Once the package updates to a newer version in nixpkgs, the rule
# becomes stale and you'll be told it can be removed.
#
# This list's rules are all community rules (community/ in the repository,
# turned on in default.nix), so this file is empty: add a rule here only for
# something the community rules shouldn't have, or to override one.
#
# Format:
# {
#   "package-name" = "version";
# }

{ }
