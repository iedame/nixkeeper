# shellcheck shell=bash
# Retakes the page's screenshots in assets/ (the README's and the social
# preview), from the live data: nix run .#screenshots, from the repository.
#
# Takes: desktop-{dark,light}.png (1280px wide, at 2x, with a panel open),
# mobile-{dark,light}.png (390px, at 2x) and social-preview.png (1280x640,
# dark), then compresses them.
#
# With the page's current code (docs/) against the published data, so what's
# shown is what's live.
#
#   nix run .#screenshots -- --browser <name or path> [--open <panel>]
#                            [--data <url>] [--port <port>]
#
# The browser has to be Chromium-based (the script uses Chromium's headless
# screenshot flags), and is always named:
#   - a nixpkgs package, fetched from this flake's nixpkgs when it's used:
#     google-chrome, chromium, ungoogled-chromium, brave, microsoft-edge,
#     vivaldi (not every one is available everywhere: chromium and
#     ungoogled-chromium are Linux-only);
#   - or a path to a browser's executable, e.g. on macOS
#     "/Applications/Chromium.app/Contents/MacOS/Chromium".
# Firefox can't be used: its headless screenshots are taken as soon as the
# page loads, before the page has fetched its data.
#
# --open picks the panel open in the desktop shots: <row>:<panel>, or none.
# The row is a package's name as the page shows it, or a position in the
# page's order (1 is the first row; past the last, the last). The panel is
# info (its details), build (its Hydra builds), update (its latest
# nixpkgs-update attempt), or auto: update if that has something to show
# (not just "none reported" or "not attempted"), else build likewise, else
# info. Default: 10:auto, far enough down that the table shows above the
# panel, whatever this copy of nixkeeper tracks. The phone shots and the
# social preview show the plain list.
#
# --data is where the data is: a URL to the folder holding index.json.
# Default: this repository's data branch on GitHub (from its origin remote).
#
# --port is the port of the local server that serves the page to the browser.
# Default: 8799.
#
# Each can also be set in the environment (OPEN, DATA, PORT); the argument
# wins.

set -euo pipefail

usage() {
	echo "Usage: nix run .#screenshots -- --browser <name or path>" >&2
	echo "  <name>: a Chromium-based browser in nixpkgs: google-chrome, chromium," >&2
	echo "          ungoogled-chromium, brave, microsoft-edge, vivaldi" >&2
	echo "  <path>: a Chromium-based browser's executable" >&2
	echo "Options:" >&2
	echo "  --open <row>:<info|build|update|auto>, or none: the panel open in the" >&2
	echo "          desktop shots; the row is a package's name or a position" >&2
	echo "          (default: 10:auto)" >&2
	echo "  --data <url>: the data, the folder with index.json (default: this" >&2
	echo "          repository's data branch on GitHub)" >&2
	echo "  --port <port>: the local server's port (default: 8799)" >&2
	echo "See scripts/screenshots.sh for more." >&2
	exit "${1:-1}"
}

browser=
while [ $# -gt 0 ]; do
	case $1 in
	--browser)
		[ $# -ge 2 ] || usage
		browser=$2
		shift 2
		;;
	--browser=*) browser=${1#--browser=} && shift ;;
	--open)
		[ $# -ge 2 ] || usage
		OPEN=$2
		shift 2
		;;
	--open=*) OPEN=${1#--open=} && shift ;;
	--data)
		[ $# -ge 2 ] || usage
		DATA=$2
		shift 2
		;;
	--data=*) DATA=${1#--data=} && shift ;;
	--port)
		[ $# -ge 2 ] || usage
		PORT=$2
		shift 2
		;;
	--port=*) PORT=${1#--port=} && shift ;;
	-h | --help) usage 0 ;;
	*)
		echo "Unknown argument: $1" >&2
		usage
		;;
	esac
done
[ -n "$browser" ] || usage

[ -f flake.nix ] && [ -d docs ] || {
	echo "Run this from the repository's root." >&2
	exit 1
}

OPEN=${OPEN:-10:auto}
[[ $OPEN == none || $OPEN =~ ^[^:]+:(info|build|update|auto)$ ]] || {
	echo "--open: expected <row>:<info|build|update|auto>, or none (got: $OPEN)" >&2
	exit 1
}
PORT=${PORT:-8799}
[[ $PORT =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || {
	echo "--port: expected a port number (got: $PORT)" >&2
	exit 1
}
if [ -z "${DATA:-}" ]; then
	# owner/repo from the origin remote: git@github.com:o/r.git or https://github.com/o/r
	repo=$(git remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
	DATA="https://raw.githubusercontent.com/$repo/data/data/"
fi
DATA=${DATA%/}/ # the folder, as the page expects it

# The data has to be there, and so does the panel asked for: the package on
# the page, and for build or update a cell that opens one (packages not in
# nixpkgs have neither).
python3 - "$DATA" "$OPEN" <<'EOF'
import json, sys, urllib.request
data, want = sys.argv[1:]
try:
    with urllib.request.urlopen(data + "index.json", timeout=30) as resp:
        rows = {row["name"]: row for row in json.load(resp)["packages"]}
except (OSError, ValueError, KeyError) as e:
    sys.exit(f"--data: couldn't read {data}index.json ({e})")
if not rows:
    sys.exit(f"--data: {data}index.json has no packages")
if want != "none":
    name, panel = want.rsplit(":", 1)
    if name.isdigit():
        # A position: the page knows its order, and takes the last row past it.
        if int(name) < 1:
            sys.exit("--open: positions start at 1")
    elif name not in rows:
        sys.exit(f"--open: no package {name!r} on the page")
    else:
        field = {"build": "builds", "update": "update"}.get(panel)
        if field and field not in rows[name]:
            sys.exit(f"--open: {name} has no {panel} panel (it's not in nixpkgs)")
EOF

case $browser in
*firefox*)
	echo "Firefox can't be used: it takes its headless screenshot before the page has" >&2
	echo "loaded its data. Use a Chromium-based browser." >&2
	exit 1
	;;
*/*) # a path
	[ -x "$browser" ] || {
		echo "Not an executable: $browser" >&2
		exit 1
	}
	chrome=$browser
	;;
*) # a nixpkgs package, from this flake's nixpkgs ($NIXPKGS, set by the app)
	[[ $browser =~ ^[A-Za-z0-9_-]+$ ]] || {
		echo "Not a package name: $browser" >&2
		exit 1
	}
	# Unfree ones (google-chrome, microsoft-edge, vivaldi) are allowed: it's
	# the one package asked for.
	pkg="(import ${NIXPKGS:?} { config.allowUnfree = true; }).\"$browser\""
	available=$(nix eval --impure --json --expr "$pkg.meta.available or false")
	if [ "$available" != true ]; then
		echo "nixpkgs has no $browser for this system: pass a path to a browser instead." >&2
		exit 1
	fi
	echo "Getting $browser from nixpkgs..."
	nix build --impure --no-link --expr "$pkg"
	chrome=$(nix eval --impure --raw --expr "(import $NIXPKGS { }).lib.getExe $pkg")
	;;
esac

work=$(mktemp -d)
site=$work/site
profile=$work/profile # a throwaway profile: nothing of yours is touched
mkdir -p "$site" "$work/out" "$profile"
server=
cleanup() {
	[ -n "$server" ] && kill "$server" 2>/dev/null
	pkill -f "user-data-dir=$profile" 2>/dev/null || true
	rm -rf "$work"
}
trap cleanup EXIT

# The page as it is in docs/, pointed at the data, and able to open a panel
# once its rows are there (?open=<row>:<panel>, as --open).
cp docs/* "$site/"
python3 - "$site/index.html" "$DATA" <<'EOF'
import sys
path, data = sys.argv[1:]
page = open(path).read()
page = page.replace(
    "<head>", f'<head><meta name="nixkeeper-data" content="{data}">', 1
)
page = page.replace(
    "</body>",
    """<script>
const want = new URLSearchParams(location.search).get('open');
if (want) {
  const at = want.lastIndexOf(':');
  const [name, panel] = [want.slice(0, at), want.slice(at + 1)];
  // A cell's panel, when it has something to show: its button isn't one of
  // the "nothing to report" ones (none reported, not attempted, ...).
  const worth = (row, kind) => {
    const b = row.querySelector(`.failure-btn[data-kind="${kind}"]`);
    return b && !b.hasAttribute('data-quiet') ? b : null;
  };
  const t = setInterval(() => {
    const rows = [...document.querySelectorAll('tr.row')];
    if (!rows.length) return;
    const row = /^[0-9]+$/.test(name)
      ? rows[Math.min(+name, rows.length) - 1]
      : rows.find((r) => r.querySelector('.n')?.textContent === name);
    if (!row) return;
    clearInterval(t);
    const button =
      panel === 'auto'
        ? worth(row, 'update') || worth(row, 'build')
        : panel === 'info'
          ? null
          : row.querySelector(`.failure-btn[data-kind="${panel}"]`);
    if (button) button.click();
    else if (panel === 'info' || panel === 'auto') row.click();
  }, 100);
}
</script></body>""",
    1,
)
open(path, "w").write(page)
EOF
# Chrome won't make a window narrower than about 500px, so the phone shots
# are of the page in a 390px frame, centred in a wider window, then cropped.
cat >"$site/phone.html" <<'EOF'
<!doctype html><meta charset="utf-8">
<style>html,body{margin:0}iframe{border:0;width:390px;height:844px;display:block;margin:0 auto}</style>
<iframe src="index.html"></iframe>
EOF

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$site" >/dev/null 2>&1 &
server=$!
sleep 1

# shot <name> <width> <height> <scale> <dark|light> <path>
shot() {
	local out=$work/out/$1.png scheme=1
	[ "$5" = dark ] && scheme=0
	"$chrome" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
		--user-data-dir="$profile" --window-size="$2,$3" \
		--force-device-scale-factor="$4" --blink-settings=preferredColorScheme=$scheme \
		--virtual-time-budget=8000 --screenshot="$out" \
		"http://127.0.0.1:$PORT/$6" >/dev/null 2>&1 &
	# Chrome writes the screenshot but doesn't always exit: wait for the file.
	for _ in $(seq 60); do
		[ -s "$out" ] && break
		sleep 1
	done
	sleep 1
	pkill -f "user-data-dir=$profile" 2>/dev/null || true
	sleep 1
	[ -s "$out" ] || {
		echo "No screenshot for $1 (is the data reachable?)" >&2
		exit 1
	}
	echo "  $1"
}

echo "Taking screenshots (data: $DATA)..."
for theme in dark light; do
	open=
	[ "$OPEN" != none ] && open="?open=$OPEN"
	shot "desktop-$theme" 1280 860 2 "$theme" "$open"
	shot "mobile-$theme" 800 844 2 "$theme" phone.html
	magick "$work/out/mobile-$theme.png" -gravity center -crop 780x1688+0+0 +repage \
		"$work/out/mobile-$theme.png"
done
shot social-preview 1280 640 1 dark ""

echo "Compressing into assets/..."
mkdir -p assets
for f in "$work"/out/*.png; do
	pngquant --quality=80-95 --strip --speed 1 --force --output "assets/$(basename "$f")" "$f"
done
du -ch assets/*.png | tail -1
echo "Done. The social preview is uploaded by hand: Settings → General → Social preview."
