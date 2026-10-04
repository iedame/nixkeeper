# Versions nixpkgs has that Repology gets wrong (calls them untrusted,
# incorrect or ignored, or compares them with a version that isn't really
# newer): a rule here counts the package as up to date while nixpkgs has
# that version.
#
# Keyed by the package's row name (its attribute, as on the page): the
# version nixpkgs has, the version Repology shows as newest elsewhere (the
# page shows it; leave it out when there's none), and why nixpkgs' version
# is right:
#
#   foo = {
#     version = "2024-01-02";
#     newest = "1.0";
#     reason = "A snapshot from after the 1.0 release.";
#   };
#
# Only Repology's verdict changes: nixkeeper's update checks and master
# still count. Once nixpkgs moves on, or Repology shows something newer than
# `newest` elsewhere (a real new release), the rule does nothing and the sync
# says it can go.
#
# This list's rules are all community rules (community/ in the repository,
# turned on in default.nix), so this file is empty: add a rule here only for
# something the community rules shouldn't have, or to override one.
{
  # keep-sorted start block=yes newline_separated=yes
  # keep-sorted end
}
