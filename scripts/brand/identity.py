"""Writes identity.html, the identity sheet, from tokens.json and the SVGs in
the same folder (default: assets/brand/). Run it after generate.py and
tokens.py.

    python3 scripts/brand/identity.py [folder]
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(HERE, "..", "..", "assets", "brand")
)
with open(os.path.join(OUT, "tokens.json")) as f:
    tokens = json.load(f)


def ink(hex_colour):
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return "#000" if 0.299 * r + 0.587 * g + 0.114 * b > 140 else "#fff"


marks = [
    ("nixkeeper-mark", "mark"),
    ("nixkeeper-status-ok", "all good"),
    ("nixkeeper-status-release", "new release"),
    ("nixkeeper-status-failure", "failure"),
    ("nixkeeper-status-vuln", "vulnerability"),
    ("nixkeeper-mark-flat", "flat"),
    ("nixkeeper-mark-rainbow", "rainbow"),
    ("nixkeeper-mark-black", "black"),
    ("nixkeeper-mark-white-on-black", "white"),
]
MEANING = {
    "ok": "up to date",
    "outdated": "outdated, a new release",
    "failed": "failed, not in nixpkgs, vulnerable",
    "warn": "can't update, marked broken",
    "merged": "on master",
    "link": "links and key UI",
}


def role_rows(theme):
    rows = []
    for name, themes in tokens["roles"].items():
        v = themes[theme]
        rows.append(
            '<div class="role">'
            f'<span class="dot" style="background:{v["fill"]}"></span>'
            f'<span style="color:{v["text"]}">{MEANING[name]}</span>'
            f'<span class="badge" style="background:{v["badge"]}">{name}</span>'
            f'<span class="tint" style="background:{v["bg"]}"></span></div>'
        )
    return "".join(rows)


ramps = "".join(
    f'<div class="name">{name}</div>'
    + "".join(
        f'<div class="sw" style="background:{c};color:{ink(c)}">{step}<br>{c}</div>'
        for step, c in ramp.items()
    )
    for name, ramp in tokens["ramps"].items()
)
FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Instrument+Sans:wght@400;700&family=JetBrains+Mono&display=swap"
)
STYLE = """
body { margin: 0; padding: 32px; font: 14px/1.4 var(--ui);
  background: #fafafa; color: #222; }
h1 { font-size: 22px; }
h2 { font-size: 16px; margin-top: 32px; }
.marks { display: flex; gap: 20px; flex-wrap: wrap; }
.marks figure { margin: 0; text-align: center; font-size: 12px; color: #555; }
.marks img { height: 110px; display: block; margin-bottom: 4px; }
.lockups { display: flex; gap: 20px; flex-wrap: wrap; }
.lockups img { height: 90px; padding: 8px; border-radius: 8px; }
.lockups img + img { background: #16181c; }
.ramps { display: grid; grid-template-columns: 90px repeat(9, 1fr); gap: 3px; }
.name { font-size: 12px; align-self: center; }
.sw { height: 46px; font: 10px/1.3 var(--mono); padding: 4px;
  border-radius: 3px; }
.themes { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.theme { padding: 16px; border-radius: 8px; }
.role { display: flex; align-items: center; gap: 10px; padding: 5px 0; }
.dot { width: 9px; height: 9px; border-radius: 50%; }
.badge { font: 11px var(--mono); color: #fff; padding: 1px 8px;
  border-radius: 10px; margin-left: auto; }
.tint { width: 60px; height: 18px; border-radius: 4px; }
"""
figures = "".join(
    f'<figure><img src="{f}.svg" alt="">{label}</figure>' for f, label in marks
)
brand = tokens["brand"]
page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>nixkeeper identity</title>
<link rel="stylesheet" href="{FONTS}">
<style>
:root {{ --ui: {tokens["fonts"]["ui"]}; --mono: {tokens["fonts"]["mono"]}; }}
{STYLE}</style></head><body>
<h1>nixkeeper identity</h1>
<p>See <a href="BRAND.md">BRAND.md</a> for the rules.
Violet {brand["violet"]} → mauve {brand["mauve"]}; the page's colours are the
NixOS guide's accents, with the page's meanings.</p>
<h2>The mark, its status versions and variants</h2>
<div class="marks">{figures}</div>
<h2>Lockups (the wordmark in Oxanium Bold, outlined)</h2>
<div class="lockups">
<img src="nixkeeper-lockup.svg" alt="">
<img src="nixkeeper-lockup-dark.svg" alt="">
</div>
<h2>Ramps (the guide's tints)</h2>
<div class="ramps">{ramps}</div>
<h2>Roles: dot, text, badge and tint, in each theme</h2>
<div class="themes">
<div class="theme" style="background:#fff">{role_rows("light")}</div>
<div class="theme" style="background:#16181c">{role_rows("dark")}</div>
</div>
</body></html>
"""
with open(os.path.join(OUT, "identity.html"), "w") as f:
    f.write(page)
print("identity.html written")
