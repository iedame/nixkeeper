"""The mark's geometry and the brand colours, shared by the brand scripts.

The mark is a flat-top hexagonal ring of three chevrons around a solid centre
hexagon (see assets/brand/BRAND.md). Coordinates are in units of the outer
hexagon's diameter, centred on the origin, y up.
"""

import math


def oklch_hex(lightness, chroma, hue):
    """An OKLCH colour as sRGB hex, clipped to the sRGB gamut."""
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_**3, m_**3, s_**3  # the long, medium and short cones
    r = 4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc
    g = -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc
    bb = -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc

    def encode(x):
        x = max(0, min(1, x))
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return "#" + "".join(f"{round(encode(v) * 255):02x}" for v in (r, g, bb))


# The brand colours: violet turning to mauve, with the contrast recipe of the
# NixOS logo's two blues (a lighter, less saturated end, turned 25 degrees in
# hue), on nixkeeper's own hues.
DARK = oklch_hex(0.50, 0.12, 288)  # brand violet: the mark's centre and 25% stop
LIGHT = oklch_hex(0.75, 0.09, 313)  # brand mauve: the 100% stop
DARK0 = oklch_hex(0.45, 0.10, 288)  # lowered lightness and chroma: the 0% stop

R = 0.5  # outer hexagon radius (diameter 1)
RI = R / 2  # inner hexagon radius
RC = R / 4  # centre hexagon radius: R, R/2, R/4, each half the one before
GAP = R / 32  # between chevrons, like the guide's lambda
_COS30 = math.cos(math.radians(30))


def line(i, rho, offset=0.0):
    """The line n.p = d through the hexagon edge i at radius rho."""
    t = math.radians(30 + 60 * i)
    return (math.cos(t), math.sin(t), rho * _COS30 + offset)


def meet(line1, line2):
    """Where two lines cross."""
    a1, b1, d1 = line1
    a2, b2, d2 = line2
    det = a1 * b2 - a2 * b1
    return ((d1 * b2 - d2 * b1) / det, (a1 * d2 - a2 * d1) / det)


def piece(k):
    """Chevron k's six corners."""
    a, b, c, p = 2 * k, 2 * k + 1, 2 * k + 2, 2 * k - 1
    outer_a, outer_b, outer_p = line(a, R), line(b, R), line(p, R)
    inner_a, inner_b = line(a, RI), line(b, RI)
    cut = line(c, RI, -GAP)  # the end cut, pulled back by the gap
    return [
        meet(outer_p, outer_a),
        meet(outer_a, outer_b),
        meet(outer_b, cut),
        meet(cut, inner_b),
        meet(inner_b, inner_a),
        meet(inner_a, outer_p),
    ]


PIECES = [piece(k) for k in range(3)]
