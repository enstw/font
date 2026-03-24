#!/usr/bin/env python3
"""Analyze font vertical metrics and block element coverage.

Usage:
    python3 utils/analyze_font_metrics.py <font_file> [font_index]
    python3 utils/analyze_font_metrics.py --diff <font_a> <font_b>

Examples:
    python3 utils/analyze_font_metrics.py dist/JetBrainsMonoNerdFont-Regular.ttf
    python3 utils/analyze_font_metrics.py /System/Library/Fonts/Menlo.ttc 0
    python3 utils/analyze_font_metrics.py /System/Library/Fonts/Supplemental/Raanana.ttc
    python3 utils/analyze_font_metrics.py --diff dist/ENSFontMonoProp-Regular-ot75ob-20v2.ttf dist/ENSFontMonoProp-Regular.ttf
"""

import sys
from fontTools.ttLib import TTFont, TTCollection


BLOCK_CHARS = {
    0x2580: "UPPER HALF BLOCK",
    0x2584: "LOWER HALF BLOCK",
    0x2588: "FULL BLOCK",
    0x258C: "LEFT HALF BLOCK",
    0x2590: "RIGHT HALF BLOCK",
    0x2591: "LIGHT SHADE",
    0x2592: "MEDIUM SHADE",
    0x2593: "DARK SHADE",
}

BOX_DRAWING_SAMPLES = {
    0x2500: "LIGHT HORIZONTAL",
    0x2501: "HEAVY HORIZONTAL",
    0x2502: "LIGHT VERTICAL",
    0x2503: "HEAVY VERTICAL",
    0x250C: "LIGHT DOWN AND RIGHT",
    0x2510: "LIGHT DOWN AND LEFT",
    0x2514: "LIGHT UP AND RIGHT",
    0x2518: "LIGHT UP AND LEFT",
    0x251C: "LIGHT VERTICAL AND RIGHT",
    0x2524: "LIGHT VERTICAL AND LEFT",
    0x253C: "LIGHT VERTICAL AND HORIZONTAL",
    0x2550: "DOUBLE HORIZONTAL",
    0x2551: "DOUBLE VERTICAL",
}

POWERLINE_CHARS = {
    0xE0B0: "PL RIGHT TRIANGLE",
    0xE0B2: "PL LEFT TRIANGLE",
    0xE0B4: "PL RIGHT SEMI-CIRCLE",
    0xE0B6: "PL LEFT SEMI-CIRCLE",
    0xE0B8: "PL LOWER-LEFT TRIANGLE",
    0xE0BA: "PL LOWER-RIGHT TRIANGLE",
    0xE0BC: "PL UPPER-LEFT TRIANGLE",
    0xE0BE: "PL UPPER-RIGHT TRIANGLE",
    0xE0D2: "PL RIGHT HALF-CIRCLE",
    0xE0D4: "PL LEFT HALF-CIRCLE",
    0xE0D6: "PL PIXELATED RIGHT",
    0xE0D7: "PL PIXELATED LEFT",
}


def analyze_font(font, name=None):
    if name:
        print(f"=== {name} ===")
    else:
        display = font["name"].getDebugName(4) or "(unknown)"
        print(f"=== {display} ===")

    head = font["head"]
    os2 = font["OS/2"]
    hhea = font["hhea"]
    upm = head.unitsPerEm

    print(f"  unitsPerEm:          {upm}")
    print()

    # OS/2 metrics
    print("  OS/2 table:")
    print(f"    sTypoAscender:     {os2.sTypoAscender}")
    print(f"    sTypoDescender:    {os2.sTypoDescender}")
    print(f"    sTypoLineGap:      {os2.sTypoLineGap}")
    print(f"    usWinAscent:       {os2.usWinAscent}")
    print(f"    usWinDescent:      {os2.usWinDescent}")
    use_typo = bool(os2.fsSelection & 0x80)
    print(f"    fsSelection:       {os2.fsSelection:#06x} (USE_TYPO_METRICS: {use_typo})")
    print()

    # hhea metrics
    print("  hhea table:")
    print(f"    ascent:            {hhea.ascent}")
    print(f"    descent:           {hhea.descent}")
    print(f"    lineGap:           {hhea.lineGap}")
    print()

    # Effective line heights
    typo_line = os2.sTypoAscender - os2.sTypoDescender + os2.sTypoLineGap
    win_line = os2.usWinAscent + os2.usWinDescent
    hhea_line = hhea.ascent - hhea.descent + hhea.lineGap

    print("  Effective line heights:")
    print(f"    Typo:  {typo_line:5d}  ({typo_line / upm:.4f} em)")
    print(f"    Win:   {win_line:5d}  ({win_line / upm:.4f} em)")
    print(f"    hhea:  {hhea_line:5d}  ({hhea_line / upm:.4f} em)")
    print()

    # Cell dimensions (macOS uses hhea when USE_TYPO is off, typo when on)
    if use_typo:
        cell_top = os2.sTypoAscender
        cell_bot = os2.sTypoDescender
        cell_src = "typo (USE_TYPO_METRICS=1)"
    else:
        cell_top = hhea.ascent
        cell_bot = hhea.descent
        cell_src = "hhea (USE_TYPO_METRICS=0)"
    cell_height = cell_top - cell_bot
    print(f"  Cell (via {cell_src}):")
    print(f"    top={cell_top}  bot={cell_bot}  height={cell_height}  ({cell_height / upm:.4f} em)")
    print()

    # Block element coverage
    cmap = font.getBestCmap()
    glyf = font.get("glyf")
    cff = font.get("CFF ")

    print("  Block element coverage:")
    for cp, name in sorted(BLOCK_CHARS.items()):
        gid = cmap.get(cp) if cmap else None
        if not gid:
            print(f"    U+{cp:04X} {name}: MISSING")
            continue

        yMin = yMax = None
        if glyf and gid in glyf:
            g = glyf[gid]
            if g.numberOfContours != 0:
                yMin, yMax = g.yMin, g.yMax
        elif cff:
            # For CFF fonts, use charstring bounds
            pass

        if yMin is not None and yMax is not None:
            gh = yMax - yMin
            coverage = gh / cell_height * 100
            gap_top = cell_top - yMax
            gap_bot = yMin - cell_bot
            print(
                f"    U+{cp:04X} {name}: "
                f"yMin={yMin} yMax={yMax} h={gh}  "
                f"coverage={coverage:.1f}%  "
                f"gap(top={gap_top}, bot={gap_bot})"
            )
        else:
            print(f"    U+{cp:04X} {name}: glyph={gid} (no outline data)")

    # Box drawing coverage (vertical connectors that should reach cell edges)
    print()
    print("  Box drawing coverage (edge-touching glyphs):")
    for cp, name in sorted(BOX_DRAWING_SAMPLES.items()):
        gid = cmap.get(cp) if cmap else None
        if not gid:
            continue

        yMin = yMax = None
        if glyf and gid in glyf:
            g = glyf[gid]
            if g.numberOfContours != 0:
                yMin, yMax = g.yMin, g.yMax

        if yMin is not None and yMax is not None:
            over_top = yMax - cell_top
            over_bot = cell_bot - yMin
            if over_top != 0 or over_bot != 0:
                print(
                    f"    U+{cp:04X} {name}: "
                    f"yMin={yMin} yMax={yMax}  "
                    f"overshoot(top={over_top}, bot={over_bot})"
                )
        elif gid:
            print(f"    U+{cp:04X} {name}: glyph={gid} (no outline data)")

    # Powerline separator coverage
    print()
    print("  Powerline separator coverage:")
    for cp, name in sorted(POWERLINE_CHARS.items()):
        gid = cmap.get(cp) if cmap else None
        if not gid:
            print(f"    U+{cp:04X} {name}: MISSING")
            continue

        yMin = yMax = None
        if glyf and gid in glyf:
            g = glyf[gid]
            if g.numberOfContours != 0:
                g.recalcBounds(glyf)
                yMin, yMax = g.yMin, g.yMax

        if yMin is not None and yMax is not None:
            gh = yMax - yMin
            coverage = gh / cell_height * 100
            over_top = yMax - cell_top
            over_bot = cell_bot - yMin
            print(
                f"    U+{cp:04X} {name}: "
                f"yMin={yMin} yMax={yMax} h={gh}  "
                f"coverage={coverage:.1f}%  "
                f"overshoot(top={over_top}, bot={over_bot})"
            )
        elif gid:
            print(f"    U+{cp:04X} {name}: glyph={gid} (no outline data)")

    # Monospace check
    print()
    hmtx = font["hmtx"]
    sample = "ABCDabcd0123 "
    widths = {}
    for ch in sample:
        gid = cmap.get(ord(ch)) if cmap else None
        if gid:
            widths[ch] = hmtx[gid][0]
    unique = set(widths.values())
    print(f"  Monospaced: {len(unique) == 1}  (unique widths: {sorted(unique)})")
    print()


ALL_CELL_EDGE_CHARS = {}
ALL_CELL_EDGE_CHARS.update(BLOCK_CHARS)
ALL_CELL_EDGE_CHARS.update(BOX_DRAWING_SAMPLES)
ALL_CELL_EDGE_CHARS.update(POWERLINE_CHARS)
# Add remaining box-drawing and block element codepoints without explicit names
for _cp in range(0x2500, 0x25A0):
    if _cp not in ALL_CELL_EDGE_CHARS:
        ALL_CELL_EDGE_CHARS[_cp] = f"U+{_cp:04X}"
for _cp in list(range(0xE0B0, 0xE0D5)) + [0xE0D6, 0xE0D7]:
    if _cp not in ALL_CELL_EDGE_CHARS:
        ALL_CELL_EDGE_CHARS[_cp] = f"U+{_cp:04X}"
for _cp in range(0x25E2, 0x25E6):
    ALL_CELL_EDGE_CHARS[_cp] = f"BLACK TRIANGLE {_cp:04X}"


def diff_fonts(path_a, path_b):
    """Compare cell-edge glyph coordinates between two fonts."""
    font_a = TTFont(path_a)
    font_b = TTFont(path_b)
    cmap_a = font_a.getBestCmap()
    cmap_b = font_b.getBestCmap()
    glyf_a = font_a.get("glyf")
    glyf_b = font_b.get("glyf")

    if not glyf_a or not glyf_b:
        print("ERROR: both fonts must be TrueType (glyf) fonts")
        sys.exit(1)

    name_a = path_a.split("/")[-1]
    name_b = path_b.split("/")[-1]
    print(f"=== Diff: {name_a}  vs  {name_b} ===")
    print()

    diffs = 0
    same = 0
    for cp in sorted(ALL_CELL_EDGE_CHARS.keys()):
        gid_a = cmap_a.get(cp)
        gid_b = cmap_b.get(cp)
        if not gid_a or not gid_b:
            continue
        if gid_a not in glyf_a or gid_b not in glyf_b:
            continue
        ga = glyf_a[gid_a]
        gb = glyf_b[gid_b]
        if ga.numberOfContours <= 0 or gb.numberOfContours <= 0:
            continue

        coords_a = list(ga.coordinates)
        coords_b = list(gb.coordinates)
        name = ALL_CELL_EDGE_CHARS.get(cp, "")

        if coords_a == coords_b:
            same += 1
            continue

        diffs += 1
        print(f"  U+{cp:04X} {name} ({gid_a}):")
        print(f"    bounds A: yMin={ga.yMin} yMax={ga.yMax}  xMin={ga.xMin} xMax={ga.xMax}")
        print(f"    bounds B: yMin={gb.yMin} yMax={gb.yMax}  xMin={gb.xMin} xMax={gb.xMax}")

        # Show per-point differences
        max_pts = max(len(coords_a), len(coords_b))
        if len(coords_a) != len(coords_b):
            print(f"    point count differs: A={len(coords_a)} B={len(coords_b)}")
        else:
            changed = []
            for j in range(max_pts):
                xa, ya = coords_a[j]
                xb, yb = coords_b[j]
                if xa != xb or ya != yb:
                    changed.append((j, xa, ya, xb, yb))
            if len(changed) <= 20:
                for j, xa, ya, xb, yb in changed:
                    dx = xb - xa
                    dy = yb - ya
                    print(f"    pt[{j:3d}]: ({xa:5d},{ya:5d}) -> ({xb:5d},{yb:5d})  delta=({dx:+d},{dy:+d})")
            else:
                print(f"    {len(changed)} points differ (showing first/last 5):")
                for j, xa, ya, xb, yb in changed[:5]:
                    dx = xb - xa
                    dy = yb - ya
                    print(f"    pt[{j:3d}]: ({xa:5d},{ya:5d}) -> ({xb:5d},{yb:5d})  delta=({dx:+d},{dy:+d})")
                print(f"    ...")
                for j, xa, ya, xb, yb in changed[-5:]:
                    dx = xb - xa
                    dy = yb - ya
                    print(f"    pt[{j:3d}]: ({xa:5d},{ya:5d}) -> ({xb:5d},{yb:5d})  delta=({dx:+d},{dy:+d})")
        print()

    print(f"  Summary: {diffs} glyphs differ, {same} identical")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--diff":
        if len(sys.argv) != 4:
            print("Usage: python3 utils/analyze_font_metrics.py --diff <font_a> <font_b>")
            sys.exit(1)
        diff_fonts(sys.argv[2], sys.argv[3])
        return

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    font_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if path.lower().endswith(".ttc"):
        ttc = TTCollection(path)
        if font_index is not None:
            analyze_font(ttc.fonts[font_index])
        else:
            for i, f in enumerate(ttc.fonts):
                analyze_font(f)
    else:
        font = TTFont(path)
        analyze_font(font)


if __name__ == "__main__":
    main()
