#!/usr/bin/env python3
"""Generate test fonts with varying cell heights or overshoot for gap testing.

Creates variants of a source font with different cell heights (in em units)
or overshoot amounts, each with a unique font name so they can be installed
side-by-side.

Usage:
    python3 utils/gen_cell_test_fonts.py <source.ttf> [--em 1.07 1.05 1.00]
    python3 utils/gen_cell_test_fonts.py <source.ttf> --range 1.10 1.00 0.02
    python3 utils/gen_cell_test_fonts.py <source.ttf> --em 1.07 --overshoot
    python3 utils/gen_cell_test_fonts.py <source.ttf> --overshoot-top 10 20 30 40 50

Options:
    --em EM [EM ...]             Specific em values to generate (default: 1.07)
    --range START END STEP       Generate a range of em values
    --overshoot                  Extend block elements to match box-drawing extents
    --overshoot-top UNITS [...]  Extend block element top edges by N font units
                                 (no metric changes, sweep to find Terminal.app gap)
    --outdir DIR                 Output directory (default: same as source)

Examples:
    # Sweep overshoot at the top to find Terminal.app gap size
    python3 utils/gen_cell_test_fonts.py dist/ENSFontMonoProp-Regular.ttf \\
        --overshoot-top 10 20 30 40 50 60

    # Single test at 1.07em
    python3 utils/gen_cell_test_fonts.py dist/ENSFontMonoProp-Regular.ttf --em 1.07

    # Sweep from 1.10em to 1.00em in 0.02 steps
    python3 utils/gen_cell_test_fonts.py dist/ENSFontMonoProp-Regular.ttf --range 1.10 1.00 0.02
"""

import argparse
import os
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


def _apply_overshoot(font, top_units, bot_units):
    """Extend block element edges beyond the cell boundary.

    Coordinates at or near ascent are moved up by top_units.
    Coordinates at or near descent are moved down by bot_units.
    Metrics are not changed.
    """
    glyf = font.get("glyf")
    cmap = font.getBestCmap()
    if not glyf or not cmap:
        return 0

    asc = font["hhea"].ascent
    desc = font["hhea"].descent
    target_top = asc + top_units
    target_bot = desc - bot_units  # bot_units=-20 -> desc+20 = shrink upward
    fixed = 0

    # All cell-edge glyphs: block elements, box drawing, powerline, triangles
    target_cps = (
        list(range(0x2500, 0x25A0)) +
        list(range(0xE0B0, 0xE0D5)) +
        [0xE0D6, 0xE0D7] +
        list(range(0x25E2, 0x25E6))
    )
    seen = set()
    for cp in target_cps:
        gid = cmap.get(cp)
        if not gid or gid not in glyf or gid in seen:
            continue
        seen.add(gid)
        g = glyf[gid]
        if g.numberOfContours <= 0:
            continue
        changed = False
        for i, (x, y) in enumerate(g.coordinates):
            if top_units and y >= asc - 10:
                g.coordinates[i] = (x, target_top)
                changed = True
            elif bot_units and y <= desc + 10:
                g.coordinates[i] = (x, target_bot)
                changed = True
        if changed:
            g.recalcBounds(glyf)
            fixed += 1

    return fixed


def gen_overshoot_font(src_path, top_units, outdir, bot_units=0, suffix=""):
    """Generate a test font with block elements extended beyond cell."""
    font = TTFont(src_path)
    fixed = _apply_overshoot(font, top_units, bot_units)

    parts = []
    if top_units:
        parts.append(f"OT{top_units}")
    if bot_units:
        parts.append(f"OB{bot_units}")
    if suffix:
        parts.append(suffix)
    label = "".join(parts) or "O0"

    # Rename to avoid conflicts
    for rec in font["name"].names:
        val = rec.toUnicode()
        new_val = val.replace("ENS Font", f"ENS Font {label}")
        new_val = new_val.replace("ENSFont", f"ENSFont{label}")
        new_val = new_val.replace("Elegant Nerd Sino", f"Elegant Nerd Sino {label}")
        if new_val != val:
            rec.string = new_val

    stem = Path(src_path).stem
    tag = label.lower()
    dst = os.path.join(outdir, f"{stem}-{tag}.ttf")
    font.save(dst)

    asc = font["hhea"].ascent
    desc = font["hhea"].descent
    print(
        f"  overshoot top={top_units:3d}u bot={bot_units:3d}u  "
        f"block=[{desc - bot_units},{asc + top_units}]  cell=[{desc},{asc}]={asc - desc}  "
        f"fixed={fixed} glyphs  -> {dst}"
    )
    return dst


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
        "--overshoot-top", nargs="+", type=int, default=None,
        metavar="UNITS",
        help="Extend block element top edges by N font units (sweep mode)"
    )
    parser.add_argument(
        "--overshoot-bot", nargs="+", type=int, default=None,
        metavar="UNITS",
        help="Extend block element bottom edges by N font units (sweep mode)"
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

    # Overshoot sweep mode: no metric changes, just extend block edges
    if args.overshoot_top or args.overshoot_bot:
        top_values = args.overshoot_top or [0]
        bot_values = args.overshoot_bot or [0]
        count = len(top_values) * len(bot_values)
        print(f"Source: {args.source}")
        print(f"Generating {count} overshoot variant(s): top={top_values} bot={bot_values}")
        print()
        for top in top_values:
            for bot in bot_values:
                gen_overshoot_font(args.source, top, outdir, bot_units=bot)
        return

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
