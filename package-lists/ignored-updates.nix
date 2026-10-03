# Versions nixpkgs-update (r-ryantm) tried to update to that should never
# count as its failure: a version upstream never really released, say. Like
# Repology's ignore rules, which keep the bot from trying them again, but
# for the attempt it already made.
#
# Keyed by the package's row name (its attribute, as on the page), then the
# version the bot tried (or, when its updateScript failed before picking one
# and the package isn't outdated, the version nixpkgs has), with why it's
# ignored:
#
#   foo."1.2.3" = "Upstream tagged it by mistake; it was never released.";
#
# A failed attempt at that version shows as superseded, with the reason; a
# failed attempt at any other version (or once a newer release is out) shows
# as failed again. When the bot's latest attempt is at another version, the
# sync says the rule can go.
#
# This list's rules are all community rules (community/ in the repository,
# turned on in default.nix), so this file is empty: add a rule here only for
# something the community rules shouldn't have, or to override one.
{ }
