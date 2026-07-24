#!/usr/bin/env python3
"""
check_mono.py - Standalone monospace conformance checker.

Usage:
    python scripts/check_mono.py <font.ttf> [--cell-width 500]

Checks:
  - post.isFixedPitch == 1
  - OS/2 PANOSE proportion == 9
  - Advance width histogram: acceptable widths are 0 or any positive multiple
    of cell_width (half-width, full-width CJK, 2-em/3-em dashes, etc.).
    Reports any non-zero, non-aligned widths with codepoint samples.
  - Terminal-furniture cell fit: box drawing, block elements, and U+2026 are
    wcwidth-narrow (terminals allot them ONE cell), so their advance must be
    exactly cell_width and their ink must stay inside the cell (small
    tolerance for the intentional tiling bleed). Guards against the v4.0
    regression where these fell through to LXGW's full-width CJK forms.

Exit 0 = pass, exit 1 = violations found.

Used for:
  - Pre-build donor validation
  - Post-build output validation in CI
"""

import argparse
import sys
from collections import defaultdict

from fontTools.ttLib import TTFont


def get_best_cmap(font: TTFont) -> dict:
    cmap_table = font["cmap"]
    for subtable in cmap_table.tables:
        if subtable.platformID == 3 and subtable.platEncID == 10:
            return dict(subtable.cmap)
    for subtable in cmap_table.tables:
        if subtable.platformID == 3 and subtable.platEncID == 1:
            return dict(subtable.cmap)
    for subtable in cmap_table.tables:
        if subtable.platformID == 0:
            return dict(subtable.cmap)
    raise ValueError("Font has no usable Unicode cmap subtable")


def check_mono(font_path: str, cell_width: int, is_mono_prop: bool = False) -> bool:
    """
    Check monospace conformance of a font file.

    Violation: any glyph with advance in (0, cell_width) — i.e. non-zero but
    narrower than the half-cell. Widths of 0 (combining marks) and >= cell_width
    (full-width CJK, double-wide Nerd icons, em-dashes) are all acceptable.
    For mono-prop fonts, PUA icons are allowed to be wider than 2 cells, but
    they MUST still be exact multiples of cell_width to satisfy fontconfig.

    Returns True if all checks pass, False if any violations found.
    """
    font = TTFont(font_path)
    violations = []

    # Check 1: post.isFixedPitch
    post = font["post"]
    if post.isFixedPitch != 1:
        violations.append(
            f"post.isFixedPitch = {post.isFixedPitch} (expected 1)"
        )

    # Check 2: OS/2 PANOSE proportion
    os2 = font["OS/2"]
    panose_prop = os2.panose.bProportion
    if panose_prop != 9:
        violations.append(
            f"OS/2 PANOSE proportion = {panose_prop} (expected 9 for mono)"
        )

    # Check 3: Advance width histogram
    cmap = get_best_cmap(font)
    hmtx = font["hmtx"]

    # Build reverse map: glyph_name -> list of codepoints
    glyph_to_cps: dict[str, list[int]] = defaultdict(list)
    for cp, gname in cmap.items():
        glyph_to_cps[gname].append(cp)

    # Acceptable advances: 0 (combining marks) or any positive multiple of
    # cell_width (half-width, full-width CJK, 2-em/3-em dashes, etc.).
    # Any non-zero advance that isn't cell-width-aligned is a violation.
    bad_widths: dict[int, list[tuple]] = defaultdict(list)
    for gname, (adv, _lsb) in hmtx.metrics.items():
        if adv == 0 or adv % cell_width == 0:
            continue

        cps = glyph_to_cps.get(gname, [])
        if cps:
            for cp in cps[:3]:
                bad_widths[adv].append((cp, gname))
        else:
            bad_widths[adv].append((None, gname))

    if bad_widths:
        for adv in sorted(bad_widths):
            samples = bad_widths[adv]
            sample_str = ", ".join(
                f"U+{cp:04X}" if cp is not None else f"<{gname}>"
                for cp, gname in samples[:5]
            )
            if len(samples) > 5:
                sample_str += f" ... +{len(samples) - 5} more"
            violations.append(
                f"Width {adv} (expected 0 or a positive multiple of {cell_width}): "
                f"{len(samples)} glyphs — e.g. {sample_str}"
            )

    # Check 4: terminal-furniture cell fit.
    # Terminals give these codepoints exactly ONE cell (wcwidth-narrow /
    # East-Asian-ambiguous), so a wider advance or wider ink overlaps the
    # neighbouring cell. ±25 units of ink tolerance covers the intentional
    # box-drawing tiling bleed; the ╱╲╳ diagonals (U+2571-2573) get more
    # because their stroke crosses the cell edge at the corner by design
    # (half a stroke width, magnified by the slope).
    furniture_probe = list(range(0x2500, 0x25A0)) + [0x2026]
    glyf = font["glyf"]
    furniture_bad = []
    for cp in furniture_probe:
        ink_tol = 60 if cp in (0x2571, 0x2572, 0x2573) else 25
        gname = cmap.get(cp)
        if gname is None or gname not in hmtx.metrics:
            continue
        adv = hmtx.metrics[gname][0]
        if adv != cell_width:
            furniture_bad.append(f"U+{cp:04X} advance {adv} != {cell_width}")
            continue
        g = glyf[gname]
        try:
            g.recalcBounds(glyf)
        except Exception:
            continue
        if g.numberOfContours == 0:
            continue
        if g.xMin < -ink_tol or g.xMax > cell_width + ink_tol:
            furniture_bad.append(
                f"U+{cp:04X} ink x[{g.xMin},{g.xMax}] outside cell [0,{cell_width}]±{ink_tol}"
            )
    if furniture_bad:
        shown = "; ".join(furniture_bad[:5])
        if len(furniture_bad) > 5:
            shown += f" ... +{len(furniture_bad) - 5} more"
        violations.append(
            f"Terminal furniture not fitted to one cell ({len(furniture_bad)} "
            f"codepoints): {shown}"
        )

    # Report
    if violations:
        print(f"FAIL: {font_path}", file=sys.stderr)
        for v in violations:
            print(f"  VIOLATION: {v}", file=sys.stderr)
        return False

    print(f"PASS: {font_path}  (acceptable widths: 0 or multiples of {cell_width})")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Check monospace conformance of a TTF font"
    )
    parser.add_argument("font", help="Path to the TTF font to check")
    parser.add_argument(
        "--cell-width",
        type=int,
        default=500,
        help="Expected half-width cell width in font units (default: 500)",
    )
    parser.add_argument(
        "--mono-prop",
        action="store_true",
        help="Skip PUA range checks for proportional Nerd Font icons",
    )
    args = parser.parse_args()

    ok = check_mono(args.font, args.cell_width, is_mono_prop=args.mono_prop)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
