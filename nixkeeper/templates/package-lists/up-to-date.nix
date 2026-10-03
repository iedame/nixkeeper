# Packages whose current version is correct, but upstream sources (like Repology)
# classify as untrusted, incorrect, or outdated.
#
# A rule here marks the package as up to date in nixkeeper, hiding the warning
# badge. Once the package updates to a newer version in nixpkgs, the rule
# becomes stale and you'll be told it can be removed.
#
# Format:
# {
#   "package-name" = "version";
# }

{
  # "some-package" = "1.2.3";
}
