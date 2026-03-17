#!/usr/bin/env python3
"""
check_mono.py - Standalone monospace conformance checker.

Usage:
    python scripts/check_mono.py <font.ttf> [--cell-width 600]

Checks:
  - post.isFixedPitch == 1
  - OS/2 PANOSE proportion == 9
  - Advance width histogram: acceptable widths are 0 or any positive multiple
    of cell_width (half-width, full-width CJK, 2-em/3-em dashes, etc.).
    Reports any non-zero, non-aligned widths with codepoint samples.

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


def check_mono(font_path: str, cell_width: int) -> bool:
    """
    Check monospace conformance of a font file.

    Violation: any glyph with advance in (0, cell_width) — i.e. non-zero but
    narrower than the half-cell. Widths of 0 (combining marks) and >= cell_width
    (full-width CJK, double-wide Nerd icons, em-dashes) are all acceptable.

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
        default=600,
        help="Expected half-width cell width in font units (default: 600)",
    )
    args = parser.parse_args()

    ok = check_mono(args.font, args.cell_width)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
