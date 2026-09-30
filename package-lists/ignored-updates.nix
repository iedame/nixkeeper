# Versions nixpkgs-update (r-ryantm) tried to update to that should never
# count as its failure: a version upstream never really released, say. Like
# Repology's ignore rules, which keep the bot from trying them again, but
# for the attempt it already made.
#
# Keyed by the package's row name (its attribute, as on the page), then the
# version the bot tried, with why it's ignored:
#
#   foo."1.2.3" = "Upstream tagged it by mistake; it was never released.";
#
# A failed attempt at that version shows as superseded, with the reason; a
# failed attempt at any other version shows as failed again. When the bot's
# latest attempt is at another version, the sync says the rule can go.
{
  # Upstream's versioning produced a 4.0-9 that was never released (its
  # download 404s). Repology ignores it now, so the bot won't try again, but
  # its failed attempt stays the latest.
  xskat."4.0-9" = "Never released: an upstream versioning mistake. Repology ignores it too.";
}
