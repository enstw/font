#!/usr/bin/env python3
"""
merge.py - Merges LXGWWenKaiTC(*) + donor font into ENS Font (Elegant Nerd Sino).

Merge strategy:
  Base:   LXGW WenKai TC / WenKai Mono TC  — CJK, Hiragana, Katakana, fullwidth, and all other glyphs
  Donor:  Non-mono: Meslo LGSDZ Nerd Font
          Mono:     Meslo LGSDZ Nerd Font Mono

All donor codepoints are transplanted into the base, overwriting any existing WenKai TC
entry at the same codepoint. WenKai TC serves as the failsafe: only codepoints absent
from the donor are retained from WenKai TC.

Usage:
    python scripts/merge.py \
        --wenkai  fonts/wenkai/LXGWWenKaiTC-Regular.ttf \
        --donor   fonts/meslo/MesloLGSDZNerdFont-Regular.ttf \
        --output  dist/ENSFont-Regular.ttf \
        --style   Regular \
        --version 3.0.0 \
        --lxgw-version 1.521 \
        --nerd-version 3.4.0
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

# Add the scripts directory to sys.path so we can import from font_lib
sys.path.insert(0, os.path.dirname(__file__))

from font_lib.cmap import get_best_cmap, ensure_cmap_subtables
from font_lib.metrics import (
    check_upm_compatibility,
    set_os2_metrics,
    compute_x_avg_char_width,
    rebuild_vmtx,
    debug_vertical_alignment,
)
from font_lib.glyphs import (
    transplant_glyphs,
    normalize_half_widths,
    fix_block_elements,
)
from font_lib.metadata import set_font_metadata, set_monospaced_metadata
from font_lib.validation import assert_donor_is_mono, validate_monospace_integrity
from font_lib.utils import parse_debug_codepoints, fix_glyph_order

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

MONO_CELL_WIDTH = 600
DEFAULT_VERTICAL_DEBUG = ["H", "x", "█", "─", "│", "中", "你"]


def merge_fonts(
    wenkai_path: str,
    donor_path: str,
    output_path: str,
    family_name: str,
    ps_family: str,
    style: str,
    version: str,
    lxgw_ver: str,
    nerd_ver: str,
    is_mono: bool = False,
    is_mono_prop: bool = False,
    debug_vertical_cps: list[int] | None = None,
) -> None:
    """
    Main merge function.

    Base:  LXGW WenKai / WenKai Mono  - CJK, Hiragana, Katakana, fullwidth glyphs
    Donor (non-mono): Meslo LGSDZ Nerd Font
    Donor (mono):     Meslo LGSDZ Nerd Font Mono

    Result is renamed to ENS Font for OFL compliance.
    """
    log.info(f"=== ENS Font Build: {style} ===")
    log.info(f"Loading LXGW WenKai (base): {wenkai_path}")
    base = TTFont(wenkai_path)
    base_before = TTFont(wenkai_path)

    log.info(f"Loading donor font: {donor_path}")
    donor = TTFont(donor_path)

    # UPM compatibility check (scale donor if needed)
    log.info("Checking UPM compatibility...")
    check_upm_compatibility(base, donor)

    # Pin output metrics to the canonical 600/1200 grid for both mono and non-mono
    # builds. While non-mono fonts may have proportional glyphs in general, ENS
    # Font's core donor (Meslo) and base (WenKai) are largely monospaced, and
    # centering glyphs within a cell-aligned grid fixes alignment issues in
    # terminal apps (especially macOS Terminal.app).
    cell_width = MONO_CELL_WIDTH

    if is_mono or is_mono_prop:
        if is_mono:
            assert_donor_is_mono(donor, donor_path)
        donor_cmap = get_best_cmap(donor)
        a_glyph = donor_cmap.get(ord('A'))
        if a_glyph and a_glyph in donor["hmtx"].metrics:
            donor_cell_width = donor["hmtx"].metrics[a_glyph][0]
            log.info(f"  Donor cell width: {donor_cell_width} units (from 'A')")
        else:
            log.warning("  Donor cell width unavailable; using canonical mono width")
        log.info(f"  Canonical mono cell width: {cell_width} units")

    # Ensure base has both BMP and full-Unicode cmap subtables
    log.info("Ensuring cmap subtable coverage...")
    ensure_cmap_subtables(base)

    # Transplant all donor glyphs into WenKai.
    # Donor codepoints overwrite WenKai entries; WenKai is the failsafe
    # and only retains codepoints the donor does not cover.
    log.info("Transplanting donor glyphs (donor overrides WenKai)...")
    donor_count = transplant_glyphs(
        src_font=donor,
        dst_font=base,
        prefix="don_",
    )
    log.info(f"  -> {donor_count} glyphs transplanted")

    # Normalize advance widths to the canonical cell grid.
    # WenKai uses a 500/1000 grid; codepoints absent from the donor leak
    # through at 500/1000 wide. Bump/snap all advances to the 600/1200 grid
    # and center the glyphs within their new cells.
    log.info("Normalizing half-width advances to cell width...")
    normalize_half_widths(base, cell_width, is_mono_prop=is_mono_prop)

    # Rebuild glyph order for internal consistency
    log.info("Rebuilding glyph order...")
    fix_glyph_order(base)

    # Suppress verbose post table glyph names (saves ~20% file size)
    base["post"].formatType = 3.0

    # Set font metadata for OFL compliance
    log.info("Setting font metadata (OFL compliance)...")
    set_font_metadata(base, family_name, ps_family, style, version, lxgw_ver, nerd_ver)

    # Set OS/2 and hhea metrics from donor reference
    log.info("Setting OS/2/hhea metrics from donor...")
    set_os2_metrics(base, donor)

    # Fix block element glyphs (U+2580-U+259F).
    # Nerd Fonts patching increased Meslo's ascent but left block element outlines
    # at the old bounds. Meslo's hinting corrects this at render time, but we strip
    # donor hinting (removeHinting). Rescale y-coordinates to fill the font cell.
    log.info("Fixing block element glyph bounds...")
    fix_block_elements(base)

    # Set monospaced metadata
    log.info(f"Setting {'monospaced' if (is_mono or is_mono_prop) else 'proportional'} metadata...")
    set_monospaced_metadata(base, (is_mono or is_mono_prop))

    # Set xAvgCharWidth using the OpenType spec weighted formula.
    # Done after normalize_half_widths so widths are already corrected.
    avg_w = compute_x_avg_char_width(base)
    base["OS/2"].xAvgCharWidth = avg_w
    log.info(f"  xAvgCharWidth set to {avg_w} (OpenType weighted formula)")

    # Validate monospace integrity
    if is_mono:
        log.info("Validating monospace integrity (extended ranges)...")
        validate_monospace_integrity(base, is_mono=True)
    elif is_mono_prop:
        log.info("Validating monospace integrity (ASCII + Latin ranges)...")
        validate_monospace_integrity(base, is_mono=True, is_mono_prop=True)
    else:
        log.info("Validating monospace integrity (ASCII only)...")
        validate_monospace_integrity(base, is_mono=False)

    # Rebuild vmtx so every glyph has a valid vertical metrics entry.
    if "vmtx" in base and "vhea" in base:
        log.info("Rebuilding vmtx for full glyph coverage...")
        rebuild_vmtx(base)

    if debug_vertical_cps:
        log.info("Logging vertical alignment diagnostics...")
        debug_vertical_alignment(base_before, donor, base, debug_vertical_cps)

    # Save
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"Saving to {output_path} ...")
    base.save(str(output))

    size_kb = output.stat().st_size // 1024
    log.info(f"=== Done: {output_path} ({size_kb:,} KB) ===")


def main():
    parser = argparse.ArgumentParser(
        description="Merge LXGWWenKaiTC(*) + donor font into ENS Font"
    )
    parser.add_argument("--wenkai", required=True, help="Path to LXGWWenKaiTC*.ttf")
    parser.add_argument("--donor", required=True, help="Path to donor TTF (Meslo LGSDZ Nerd Font or Meslo LGSDZ Nerd Font Mono)")
    parser.add_argument("--output", required=True, help="Output .ttf path")
    parser.add_argument(
        "--family-name",
        default="ENS Font",
        help="Name table family name (default: ENS Font)",
    )
    parser.add_argument(
        "--ps-family",
        default="ENSFont",
        help="PostScript name prefix (default: ENSFont)",
    )
    parser.add_argument(
        "--style",
        required=True,
        choices=["Light", "Regular", "Bold"],
        help="Font style",
    )
    parser.add_argument(
        "--version", required=True, help="Packaging version (e.g. 1.0.0)"
    )
    parser.add_argument(
        "--lxgw-version", required=True, help="LXGW WenKai upstream version"
    )
    parser.add_argument(
        "--nerd-version", required=True, help="Nerd Fonts upstream version"
    )
    parser.add_argument("--mono", action="store_true", help="Assert that the output should be monospaced")
    parser.add_argument("--mono-prop", action="store_true", help="Assert monospaced metadata but allow proportional Nerd Font icons")
    parser.add_argument(
        "--debug-vertical",
        nargs="*",
        metavar="GLYPH",
        help=(
            "Log base/donor/merged glyph bounds for selected codepoints. "
            "Accepts literal characters or U+XXXX values. Defaults to a representative set "
            "if provided without arguments."
        ),
    )
    args = parser.parse_args()

    debug_vertical_cps = None
    if args.debug_vertical is not None:
        selectors = args.debug_vertical or DEFAULT_VERTICAL_DEBUG
        debug_vertical_cps = parse_debug_codepoints(selectors)

    merge_fonts(
        wenkai_path=args.wenkai,
        donor_path=args.donor,
        output_path=args.output,
        family_name=args.family_name,
        ps_family=args.ps_family,
        style=args.style,
        version=args.version,
        lxgw_ver=args.lxgw_version,
        nerd_ver=args.nerd_version,
        is_mono=args.mono,
        is_mono_prop=args.mono_prop,
        debug_vertical_cps=debug_vertical_cps,
    )


if __name__ == "__main__":
    main()
