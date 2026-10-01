"""Writes every SVG of the mark into a folder (default: assets/brand/).

    python3 scripts/brand/generate.py [folder]

Run through `nix run .#brand`, which also refreshes the tokens, the identity
sheet and the page's favicon.
"""

import math
import os
import sys

from geometry import DARK, DARK0, LIGHT, PIECES, RC, oklch_hex

S = 1000  # the mark's width in SVG units
MH = math.sqrt(3) / 2 * S  # its height (flat-top hexagon)

BRAND = (DARK0, DARK, LIGHT)  # the gradient's stops: 0%, 25%, 100%
RAINBOW = [("#c10100", "#ff6705"), ("#fdb00b", "#029b3b"), ("#0088cc", "#5a37bb")]

# The page's colour for each signal (the guide's accents, chroma 0.12), and the
# chevron it colours: 0 releases, 1 build and update failures, 2
# vulnerabilities. "ok" is the releases chevron in green: up to date, all good.
STATUSES = {
    "ok": (152, 0),  # Zambian Green
    "release": (54, 0),  # Persian Orange
    "failure": (16, 1),  # Norwegian Pink
    "vuln": (16, 2),  # Norwegian Pink
}


def accent(hue):
    """A status colour's gradient stops."""
    return tuple(oklch_hex(lightness, 0.12, hue) for lightness in (0.58, 0.65, 0.72))


def polygon(points, ox, oy, scale):
    """Points in mark units to SVG coordinates, and their path."""
    xy = [
        (ox + (S / 2 + x * S) * scale, oy + (S / 2 - y * S) * scale) for x, y in points
    ]
    return xy, "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in xy) + " Z"


def mark(spec, ox=0, oy=0, scale=1.0, ids="m", centre=None):
    """The mark's gradients and paths. spec: "gradient", "rainbow", a flat
    colour ("#rrggbb"), or three chevrons' stops."""
    flat = isinstance(spec, str) and spec.startswith("#")
    defs, body = [], []
    for k, points in enumerate(PIECES):
        xy, d = polygon(points, ox, oy, scale)
        if flat:
            body.append(f'<path d="{d}" fill="{spec}"/>')
            continue
        if spec == "gradient":
            stops = [(0, BRAND[0]), (0.25, BRAND[1]), (1, BRAND[2])]
        elif spec == "rainbow":
            stops = [(0, RAINBOW[k][0]), (1, RAINBOW[k][1])]
        else:
            c = spec[k]
            stops = [(0, c[0]), (0.25, c[1]), (1, c[2])]
        start = ((xy[0][0] + xy[5][0]) / 2, (xy[0][1] + xy[5][1]) / 2)
        end = ((xy[2][0] + xy[3][0]) / 2, (xy[2][1] + xy[3][1]) / 2)
        gid = f"{ids}{k}"
        defs.append(
            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
            f'x1="{start[0]:.2f}" y1="{start[1]:.2f}" '
            f'x2="{end[0]:.2f}" y2="{end[1]:.2f}">'
            + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
            + "</linearGradient>"
        )
        body.append(f'<path d="{d}" fill="url(#{gid})"/>')
    hexagon = [
        (RC * math.cos(math.radians(60 * i)), RC * math.sin(math.radians(60 * i)))
        for i in range(6)
    ]
    fill = centre or (spec if flat else DARK)
    body.append(f'<path d="{polygon(hexagon, ox, oy, scale)[1]}" fill="{fill}"/>')
    return defs, body


def svg(width, height, body, defs, bg=None):
    """A standalone SVG, titled for screen readers (the page's linter requires
    a title in docs/)."""
    rect = f'<rect width="100%" height="100%" fill="{bg}"/>' if bg else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width:.0f} {height:.0f}">'
        f"<title>nixkeeper</title><defs>{''.join(defs)}</defs>"
        f"{rect}{''.join(body)}</svg>\n"
    )


def write(folder, name, content):
    with open(os.path.join(folder, f"{name}.svg"), "w") as f:
        f.write(content)


def main(folder):
    os.makedirs(folder, exist_ok=True)
    clear = MH / 4  # clearspace: a quarter of the mark's height on each side
    oy = clear - (S - MH) / 2

    def standalone(spec, name, bg=None):
        defs, body = mark(spec, clear, oy, ids=name)
        write(folder, name, svg(S + 2 * clear, MH + 2 * clear, body, defs, bg))

    standalone("gradient", "nixkeeper-mark")
    standalone("rainbow", "nixkeeper-mark-rainbow")
    standalone(DARK, "nixkeeper-mark-flat")
    standalone("#000000", "nixkeeper-mark-black")
    standalone("#ffffff", "nixkeeper-mark-white-on-black", bg="#000000")
    for key, (hue, chevron) in STATUSES.items():
        spec = [BRAND, BRAND, BRAND]
        spec[chevron] = accent(hue)
        standalone(spec, f"nixkeeper-status-{key}")

    # The favicon: cropped tight, no clearspace.
    defs, body = mark("gradient", 0, -(S - MH) / 2, ids="fav")
    write(folder, "favicon", svg(S, MH, body, defs))

    # The lockups: the wordmark's cap height is half the mark's height, and the
    # gap between them is 3/8 of the cap height.
    name = "nixkeeper"
    for fill, file, bg in (
        ("#000000", "nixkeeper-lockup", None),
        ("#ffffff", "nixkeeper-lockup-dark", "#000000"),
    ):
        scale = 0.5
        mark_h = MH * scale
        pad = mark_h / 2
        cap_h = mark_h / 2
        defs, body = mark("gradient", pad, pad - (S - MH) / 2 * scale, scale, ids=file)
        x = pad + S * scale + cap_h * 3 / 8
        base = pad + mark_h / 2 + cap_h / 2
        size = cap_h / 0.70
        # The page's typeface, not Route 159 (the NixOS logotype's): live text
        # for now, to be converted to outlines before the lockup is used.
        body.append(
            f'<text x="{x:.1f}" y="{base:.1f}" '
            "font-family=\"'Instrument Sans', system-ui, sans-serif\" "
            f'font-weight="700" font-size="{size:.1f}" fill="{fill}">{name}</text>'
        )
        width = x + size * 0.55 * len(name) + pad
        write(folder, file, svg(width, mark_h + 2 * pad, body, defs, bg))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    main(
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(here, "..", "..", "assets", "brand")
    )
