#!/usr/bin/env python3
"""Generate test fonts with varying cell heights for gap testing.

Creates variants of a source font with different cell heights (in em units),
each with a unique font name so they can be installed side-by-side.
No glyph outlines are modified — only vertical metrics change.

Usage:
    python3 utils/gen_cell_test_fonts.py <source.ttf> [--em 1.07 1.05 1.00]
    python3 utils/gen_cell_test_fonts.py <source.ttf> --range 1.10 1.00 0.02
    python3 utils/gen_cell_test_fonts.py <source.ttf> --em 1.07 --overshoot

Options:
    --em EM [EM ...]       Specific em values to generate (default: 1.07)
    --range START END STEP Generate a range of em values
    --overshoot            Extend block elements (U+2580-U+259F) to match
                           box-drawing extents (for combo testing)
    --outdir DIR           Output directory (default: same as source)

Examples:
    # Single test at 1.07em
    python3 utils/gen_cell_test_fonts.py dist/ENSFontMonoProp-Regular.ttf --em 1.07

    # Sweep from 1.10em to 1.00em in 0.02 steps
    python3 utils/gen_cell_test_fonts.py dist/ENSFontMonoProp-Regular.ttf --range 1.10 1.00 0.02

    # 1.07em with block element overshoot
    python3 utils/gen_cell_test_fonts.py dist/ENSFontMonoProp-Regular.ttf --em 1.07 --overshoot
"""

import argparse
import os
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


def gen_test_font(src_path, target_em, outdir, overshoot=False):
    """Generate a single test font at the given em height."""
    font = TTFont(src_path)
    hhea = font["hhea"]
    os2 = font["OS/2"]
    upm = font["head"].unitsPerEm

    old_asc = hhea.ascent
    old_desc = hhea.descent
    old_cell = old_asc - old_desc

    target_cell = round(upm * target_em)
    ratio = old_asc / old_cell
    new_asc = round(target_cell * ratio)
    new_desc = new_asc - target_cell

    # Update all metric tables
    hhea.ascent = new_asc
    hhea.descent = new_desc
    hhea.lineGap = 0
    os2.sTypoAscender = new_asc
    os2.sTypoDescender = new_desc
    os2.sTypoLineGap = 0
    os2.usWinAscent = new_asc
    os2.usWinDescent = abs(new_desc)
    os2.fsSelection |= 0x80

    # Extend block elements to match box-drawing extents if requested
    if overshoot:
        glyf = font.get("glyf")
        cmap = font.getBestCmap()
        if glyf and cmap:
            # Find box-drawing vertical extents
            box_top = None
            box_bot = None
            for cp in [0x2502, 0x2503, 0x2551]:
                gid = cmap.get(cp)
                if gid and gid in glyf:
                    g = glyf[gid]
                    if g.numberOfContours > 0:
                        if box_top is None or g.yMax > box_top:
                            box_top = g.yMax
                        if box_bot is None or g.yMin < box_bot:
                            box_bot = g.yMin

            if box_top is not None and box_bot is not None:
                fixed = 0
                for cp in range(0x2580, 0x25A0):
                    gid = cmap.get(cp)
                    if not gid or gid not in glyf:
                        continue
                    g = glyf[gid]
                    if g.numberOfContours <= 0:
                        continue
                    changed = False
                    for i, (x, y) in enumerate(g.coordinates):
                        if y >= old_asc:
                            g.coordinates[i] = (x, box_top)
                            changed = True
                        elif y <= old_desc:
                            g.coordinates[i] = (x, box_bot)
                            changed = True
                    if changed:
                        g.recalcBounds(glyf)
                        fixed += 1
                print(f"  Extended {fixed} block glyphs to [{box_bot}, {box_top}]")

    # Build label from em value (e.g. 1.07 -> "107")
    label = f"{round(target_em * 100)}"
    suffix = "C" if overshoot else ""

    # Rename to avoid conflicts
    for rec in font["name"].names:
        val = rec.toUnicode()
        new_val = val.replace("ENS Font", f"ENS Font {label}{suffix}")
        new_val = new_val.replace("ENSFont", f"ENSFont{label}{suffix}")
        new_val = new_val.replace("Elegant Nerd Sino", f"Elegant Nerd Sino {label}{suffix}")
        if new_val != val:
            rec.string = new_val

    # Output path
    stem = Path(src_path).stem
    dst = os.path.join(outdir, f"{stem}-{label}em{suffix.lower()}.ttf")
    font.save(dst)

    blk_bot = new_desc - old_desc
    blk_top = old_asc - new_asc
    ps_name = font["name"].getDebugName(6)
    print(
        f"  {label}{suffix}em  cell={target_cell}  "
        f"asc={new_asc} desc={new_desc}  "
        f"blk_over={blk_top}/{blk_bot}  "
        f"ps={ps_name}  -> {dst}"
    )
    return dst


def main():
    parser = argparse.ArgumentParser(
        description="Generate test fonts with varying cell heights"
    )
    parser.add_argument("source", help="Source TTF font file")
    parser.add_argument(
        "--em", nargs="+", type=float, default=None,
        help="Target em values (e.g. 1.07 1.05 1.00)"
    )
    parser.add_argument(
        "--range", nargs=3, type=float, metavar=("START", "END", "STEP"),
        help="Generate a range: START END STEP (e.g. 1.10 1.00 0.02)"
    )
    parser.add_argument(
        "--overshoot", action="store_true",
        help="Extend block elements to match box-drawing extents"
    )
    parser.add_argument(
        "--outdir", default=None,
        help="Output directory (default: same as source)"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        print(f"Error: {args.source} not found", file=sys.stderr)
        sys.exit(1)

    outdir = args.outdir or os.path.dirname(args.source) or "."
    os.makedirs(outdir, exist_ok=True)

    # Build list of em values
    em_values = []
    if args.range:
        start, end, step = args.range
        if start > end:
            step = -abs(step)
        v = start
        while (step > 0 and v >= end - 0.001) or (step < 0 and v >= end - 0.001):
            em_values.append(round(v, 4))
            v += step
    elif args.em:
        em_values = args.em
    else:
        em_values = [1.07]

    print(f"Source: {args.source}")
    print(f"Generating {len(em_values)} variant(s): {em_values}")
    print()

    for em in em_values:
        gen_test_font(args.source, em, outdir, overshoot=args.overshoot)


if __name__ == "__main__":
    main()
