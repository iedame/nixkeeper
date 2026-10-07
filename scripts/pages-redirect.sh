# shellcheck shell=bash
# Writes, into DIR, a GitHub Pages site that sends every visitor on to
# SITE: for an instance served from its own site (Cloudflare,
# CLOUDFLARE_SITE_URL; docs/all-packages.md), so its <owner>.github.io
# address isn't a second copy of the dashboard, reading its data the slow
# way. Run by .github/workflows/pages.yml instead of publishing the page.
#
#   bash scripts/pages-redirect.sh SITE DIR
#
# A link keeps what it showed: the search, filters and view (?q=, ?view=,
# ...) and any #fragment go along. Every address on Pages does the same
# (404.html), to SITE's front page. Without JavaScript, a plain redirect to
# SITE.

set -euo pipefail

site=${1:-}
dir=${2:-}
if [ -z "$site" ] || [ -z "$dir" ]; then
  echo "usage: bash scripts/pages-redirect.sh SITE DIR" >&2
  exit 2
fi
case "$site" in
https://*) ;;
*)
  echo "::error::The site ($site) should start with https://." >&2
  exit 1
  ;;
esac
# Written into the page as is: nothing that could end an attribute or a
# string.
if [[ "$site" =~ [\"\'\<\>\\[:space:]] ]]; then
  echo "::error::The site ($site) has characters a URL shouldn't." >&2
  exit 1
fi
site=${site%/}/

rm -rf "$dir"
mkdir -p "$dir"
for page in index.html 404.html; do
  cat >"$dir/$page" <<EOF
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex">
<title>nixkeeper has moved</title>
<link rel="canonical" href="$site">
<script>location.replace('$site' + location.search + location.hash);</script>
<meta http-equiv="refresh" content="0; url=$site">
</head>
<body>
<p>nixkeeper is now at <a href="$site">$site</a>.</p>
</body>
</html>
EOF
done
echo "Pages sends visitors to $site."
