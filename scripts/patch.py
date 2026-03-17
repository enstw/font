#!/usr/bin/env python3
"""
patch.py - Grafts Nerd Fonts PUA glyphs from NerdFontsSymbolsOnly into a base TTF.

This helper is retained for cases where a text donor font needs Nerd Fonts PUA
symbols injected before merge.py runs. The Meslo LGSDZ pipeline does not use it
because the selected Nerd Fonts donors already include the patch set.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from merge import (
    check_upm_compatibility,
    ensure_cmap_subtables,
    fix_glyph_order,
    rebuild_vmtx,
    transplant_glyphs,
)

from fontTools.ttLib import TTFont

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def patch_font(input_path: str, symbols_path: str, output_path: str) -> None:
    """
    Graft all glyphs from NerdFontsSymbolsOnly into a base donor TTF.

    NerdFontsSymbolsOnly contains only PUA icon glyphs — it is safe to transplant
    all of its codepoints into the base donor without overwriting text glyphs,
    since there is no overlap between PUA ranges and normal text coverage.
    """
    log.info(f"=== Nerd Fonts Patch: {Path(input_path).name} ===")

    log.info(f"Loading base font: {input_path}")
    base = TTFont(input_path)

    log.info(f"Loading Nerd Fonts symbols: {symbols_path}")
    symbols = TTFont(symbols_path)

    log.info("Step 1: Checking UPM compatibility...")
    check_upm_compatibility(base, symbols)

    log.info("Step 2: Ensuring cmap subtable coverage (BMP format 4 + full Unicode format 12)...")
    ensure_cmap_subtables(base)

    log.info("Step 3: Transplanting Nerd Fonts PUA glyphs into donor font...")
    count = transplant_glyphs(src_font=symbols, dst_font=base, prefix="nrd_")
    log.info(f"  -> {count} glyphs transplanted")

    log.info("Step 4: Rebuilding glyph order for internal consistency...")
    fix_glyph_order(base)

    # Suppress post table glyph names — saves ~20% file size, not needed for intermediate file
    base["post"].formatType = 3.0

    if "vmtx" in base and "vhea" in base:
        log.info("Step 5: Rebuilding vmtx for full glyph coverage...")
        rebuild_vmtx(base)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"Step 6: Saving to {output_path} ...")
    base.save(str(output))

    size_kb = output.stat().st_size // 1024
    log.info(f"=== Done: {output_path} ({size_kb:,} KB) ===")


def main():
    parser = argparse.ArgumentParser(
        description="Graft Nerd Fonts PUA glyphs into a base TTF"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to base TTF"
    )
    parser.add_argument(
        "--symbols", required=True,
        help="Path to NerdFontsSymbolsOnly TTF"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output patched TTF path"
    )
    args = parser.parse_args()

    patch_font(args.input, args.symbols, args.output)


if __name__ == "__main__":
    main()
