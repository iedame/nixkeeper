"""The wordmark as outlines: "nixkeeper" in Oxanium Bold, shaped by HarfBuzz
(the font's own spacing and kerning) and drawn as one SVG path, so it looks
the same everywhere without the font.

The font file comes from the flake (`nix run .#brand` passes its path); the
outlines in the generated SVGs are all that ends up in the repository.
"""

import uharfbuzz as hb

NAME = "nixkeeper"
WEIGHT = 700  # Oxanium is a variable font: Bold


class _PathPen:
    """Collects a glyph's outline as SVG path commands, from font units (y up)
    to SVG coordinates (y down) at a scale and an origin. The method names are
    the pen protocol HarfBuzz draws with."""

    def __init__(self, scale, y):
        self.scale, self.x, self.y, self.d = scale, 0.0, y, []

    def _p(self, x, y):
        return f"{self.x + x * self.scale:.1f},{self.y - y * self.scale:.1f}"

    def moveTo(self, pt):
        self.d.append("M" + self._p(*pt))

    def lineTo(self, pt):
        self.d.append("L" + self._p(*pt))

    def curveTo(self, *pts):
        self.d.append("C" + " ".join(self._p(*q) for q in pts))

    def qCurveTo(self, *pts):
        self.d.append("Q" + " ".join(self._p(*q) for q in pts))

    def closePath(self):
        self.d.append("Z")


def outline(font_path, x, baseline, x_height):
    """The wordmark's path, starting at x on the baseline, scaled so its
    x-height is x_height; and where it ends."""
    font = hb.Font(hb.Face(hb.Blob.from_file_path(font_path)))
    font.set_variations({"wght": WEIGHT})
    buf = hb.Buffer()
    buf.add_str(NAME)
    buf.guess_segment_properties()
    hb.shape(font, buf)
    measured = font.get_glyph_extents(font.get_nominal_glyph(ord("x"))).y_bearing
    pen = _PathPen(x_height / measured, baseline)
    pen.x = x
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
        start = pen.x
        pen.x += pos.x_offset * pen.scale
        font.draw_glyph_with_pen(info.codepoint, pen)
        pen.x = start + pos.x_advance * pen.scale
    return "".join(pen.d), pen.x
