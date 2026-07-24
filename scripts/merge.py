#!/usr/bin/env python3
"""
merge.py - Merges LXGWWenKaiTC(*) + Nerd Fonts symbols into ENS Font (Elegant Nerd Sino).

Merge strategy:
  Base:      LXGW WenKai TC / WenKai Mono TC  — ASCII, Latin, CJK, kana,
             fullwidth: every text glyph
  Donor:     Symbols Nerd Font (Mono flavor for the strict-mono build) — PUA
             icons only
  Furniture: Meslo LGSDZ Nerd Font Mono (pinned) — box drawing, block
             elements, and curated ambiguous-width symbols for Mono and
             Mono Prop builds. Terminals allot these ONE cell; LXGW draws
             them CJK full-width, so its ink would overlap the next cell.

All donor codepoints are transplanted into the base, overwriting any existing WenKai TC
entry at the same codepoint (in practice only the handful of Powerline glyphs both
fonts carry). The furniture donor then overrides its curated codepoint set. WenKai TC
provides everything else, including the entire ASCII range.

Usage:
    python scripts/merge.py \
        --wenkai  fonts/wenkai/LXGWWenKaiMonoTC-Regular.ttf \
        --donor   fonts/symbols/SymbolsNerdFontMono-Regular.ttf \
        --furniture-donor fonts/meslo/MesloLGSDZNerdFontMono-Regular.ttf \
        --output  dist/ENSFontMono-Regular.ttf \
        --style   Regular \
        --mono \
        --version 4.1.0 \
        --lxgw-version 1.522 \
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

from font_lib.cmap import ensure_cmap_subtables, dealias_cmap
from font_lib.metrics import (
    check_upm_compatibility,
    set_os2_flags,
    compute_x_avg_char_width,
    rebuild_vmtx,
    debug_vertical_alignment,
)
from font_lib.glyphs import (
    transplant_glyphs,
    transplant_terminal_furniture,
    normalize_half_widths,
    fix_block_elements,
    fit_nerd_icons,
)
from font_lib.metadata import set_font_metadata, set_monospaced_metadata
from font_lib.validation import validate_monospace_integrity
from font_lib.utils import parse_debug_codepoints, fix_glyph_order

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# The LXGW native half/full grid. The base font supplies ASCII, so the cell
# is simply LXGW Mono TC's own 500/1000 design grid.
MONO_CELL_WIDTH = 500
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
    furniture_path: str | None = None,
    debug_vertical_cps: list[int] | None = None,
) -> None:
    """
    Main merge function.

    Base:      LXGW WenKai / WenKai Mono  - all text glyphs including ASCII/Latin
    Donor:     Symbols Nerd Font (Mono flavor for strict-mono builds) - PUA icons
    Furniture: Meslo (pinned) - box drawing / block elements / ambiguous-width
               terminal symbols, Mono and Mono Prop builds only

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

    # LXGW's native half/full grid; Mono variants keep it as the cell grid.
    cell_width = MONO_CELL_WIDTH

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

    # Transplant terminal furniture (box drawing, block elements, curated
    # ambiguous-width symbols) from the pinned Meslo donor. Terminals allot
    # these codepoints ONE cell, but LXGW draws them CJK-style on the full
    # em — the ink would overlap the next cell. Runs after the icon
    # transplant so furniture wins any codepoint both donors carry.
    if furniture_path and (is_mono or is_mono_prop):
        log.info(f"Loading terminal-furniture donor: {furniture_path}")
        furniture = TTFont(furniture_path)
        check_upm_compatibility(base, furniture)
        log.info("Transplanting terminal furniture (furniture overrides all)...")
        transplant_terminal_furniture(base, furniture, cell_width)
    elif furniture_path:
        log.info("Furniture donor given but build is proportional — keeping LXGW forms.")

    # Fit transplanted Nerd icons to the base font's geometry.
    # The symbols-only donor is not pre-fitted to any text font's cell (that
    # used to be the Nerd Fonts patcher's job). Powerline separators stretch
    # to fill the line box in every variant; strict Mono additionally scales
    # every icon into a single 500-unit cell. Other builds keep the donor's
    # native icon size — deliberately NOT rescaled to match the text (larger
    # icons preferred; see AGENTS.md).
    log.info("Fitting Nerd icons to base geometry...")
    fit_nerd_icons(
        base,
        donor,
        cell_width=cell_width if (is_mono or is_mono_prop) else None,
        fit_all=is_mono,
    )

    # Normalize advance widths to the cell grid for monospaced builds.
    # The base already lives on the 500/1000 grid, so this is a safety net
    # for off-grid stragglers and proportional donor icons (mono-prop snaps
    # them to cell multiples). Proportional builds skip this to maintain
    # variable-width punctuation, CJK, and Nerd Font icons.
    if is_mono or is_mono_prop:
        log.info("Normalizing half-width advances to cell width...")
        normalize_half_widths(base, cell_width, is_mono_prop=is_mono_prop)
    else:
        log.info("Skipping grid normalization for proportional build.")

    # De-alias the merged cmap so every codepoint gets its own glyph.
    # WenKai maps variant codepoints (錄/録, 內/内, U+3000/U+2003) onto shared
    # glyphs; a PDF's ToUnicode CMap can map a glyph back to only ONE codepoint,
    # so text copied/searched in generated PDFs comes back as the variant.
    # Duplicate-and-remap keeps rendering identical while making extraction exact.
    log.info("De-aliasing cmap (one glyph per codepoint)...")
    n_dealiased = dealias_cmap(base)
    log.info(f"  -> {n_dealiased} alias codepoints remapped to duplicate glyphs")

    # Rebuild glyph order for internal consistency
    log.info("Rebuilding glyph order...")
    fix_glyph_order(base)

    # Suppress verbose post table glyph names (saves ~20% file size)
    base["post"].formatType = 3.0

    # Set font metadata for OFL compliance
    log.info("Setting font metadata (OFL compliance)...")
    set_font_metadata(base, family_name, ps_family, style, version, lxgw_ver, nerd_ver)

    # OS/2 housekeeping. Vertical metrics stay LXGW's own: the base supplies
    # the text glyphs, so its line rhythm is the product's rhythm.
    log.info("Setting OS/2 flags (metrics kept from LXGW base)...")
    set_os2_flags(base, donor)

    # Fix block element / box drawing glyph bounds.
    # LXGW draws them on its typographic design box, but terminals size the
    # cell from hhea metrics; rescale so stacked blocks and vertical strokes
    # tile without horizontal gaps.
    log.info("Fixing block element / box drawing glyph bounds...")
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
    parser.add_argument("--donor", required=True, help="Path to donor TTF (SymbolsNerdFont or SymbolsNerdFontMono)")
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
        "--furniture-donor",
        default=None,
        help=(
            "Path to a monospaced terminal-furniture donor TTF (pinned Meslo). "
            "Supplies box drawing / block elements / ambiguous-width symbols "
            "for --mono and --mono-prop builds; ignored otherwise."
        ),
    )
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
        furniture_path=args.furniture_donor,
        debug_vertical_cps=debug_vertical_cps,
    )


if __name__ == "__main__":
    main()
