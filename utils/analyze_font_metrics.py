#!/usr/bin/env python3
"""Analyze font vertical metrics and block element coverage.

Usage:
    python3 utils/analyze_font_metrics.py <font_file> [font_index]

Examples:
    python3 utils/analyze_font_metrics.py dist/JetBrainsMonoNerdFont-Regular.ttf
    python3 utils/analyze_font_metrics.py /System/Library/Fonts/Menlo.ttc 0
    python3 utils/analyze_font_metrics.py /System/Library/Fonts/Supplemental/Raanana.ttc
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


def main():
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
