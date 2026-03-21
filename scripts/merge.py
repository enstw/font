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
import copy
import logging
from datetime import datetime
import sys
from pathlib import Path

from fontTools import ttLib
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _n_a_m_e

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

MONO_CELL_WIDTH = 600
DEFAULT_VERTICAL_DEBUG = ["H", "x", "█", "─", "│", "中", "你"]


def get_best_cmap(font: TTFont) -> dict:
    """
    Extract the best available Unicode cmap from a font.
    Preference order: Windows full Unicode (format 12) > Windows BMP (format 4) > Unicode platform.
    Returns {codepoint: glyph_name}.
    """
    cmap_table = font["cmap"]

    # Try Windows Unicode Full (format 12) - covers full Unicode range including Plane 15 PUA
    for subtable in cmap_table.tables:
        if subtable.platformID == 3 and subtable.platEncID == 10:
            return dict(subtable.cmap)

    # Fall back to Windows BMP (format 4)
    for subtable in cmap_table.tables:
        if subtable.platformID == 3 and subtable.platEncID == 1:
            return dict(subtable.cmap)

    # Fall back to any Unicode platform subtable
    for subtable in cmap_table.tables:
        if subtable.platformID == 0:
            return dict(subtable.cmap)

    raise ValueError("Font has no usable Unicode cmap subtable")


def ensure_cmap_subtables(font: TTFont) -> None:
    """
    Ensure the font has both a BMP (format 4) and full Unicode (format 12) cmap subtable.
    Required after adding non-BMP codepoints (e.g., Nerd Fonts Plane 15 PUA).
    """
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

    cmap_table = font["cmap"]
    has_format4 = any(t.format == 4 for t in cmap_table.tables)
    has_format12 = any(t.format == 12 for t in cmap_table.tables)
    best = get_best_cmap(font)

    if not has_format4:
        log.info("Adding BMP cmap format 4 subtable")
        sub = CmapSubtable.newSubtable(4)
        sub.platformID = 3
        sub.platEncID = 1
        sub.language = 0
        sub.cmap = {k: v for k, v in best.items() if k <= 0xFFFF}
        cmap_table.tables.append(sub)

    if not has_format12:
        log.info("Adding full-Unicode cmap format 12 subtable")
        sub = CmapSubtable.newSubtable(12)
        sub.platformID = 3
        sub.platEncID = 10
        sub.language = 0
        sub.cmap = dict(best)
        cmap_table.tables.append(sub)


def parse_debug_codepoints(values: list[str]) -> list[int]:
    """
    Parse vertical-debug glyph selectors from characters or U+XXXX values.
    """
    codepoints = []
    for value in values:
        if value.startswith(("U+", "u+")):
            codepoints.append(int(value[2:], 16))
        elif value.startswith(("0x", "0X")):
            codepoints.append(int(value, 16))
        elif len(value) == 1:
            codepoints.append(ord(value))
        else:
            raise ValueError(
                f"Unsupported debug glyph selector '{value}'. Use a literal character or U+XXXX."
            )
    return codepoints


def get_glyph_bounds(font: TTFont, glyph_name: str) -> tuple[int | None, int | None]:
    """
    Return (yMin, yMax) for a glyph if bounds can be computed.
    """
    glyf = font["glyf"]
    glyph = glyf[glyph_name]
    try:
        glyph.recalcBounds(glyf)
    except Exception:
        return (None, None)
    return (getattr(glyph, "yMin", None), getattr(glyph, "yMax", None))


def log_vertical_metrics(font: TTFont, label: str) -> None:
    """
    Log the line-height metrics that affect horizontal layout.
    """
    os2 = font["OS/2"]
    hhea = font["hhea"]
    log.info(
        "%s metrics: UPM=%s hhea=(%s,%s,%s) typo=(%s,%s,%s) win=(%s,%s)",
        label,
        font["head"].unitsPerEm,
        hhea.ascent,
        hhea.descent,
        hhea.lineGap,
        os2.sTypoAscender,
        os2.sTypoDescender,
        os2.sTypoLineGap,
        os2.usWinAscent,
        os2.usWinDescent,
    )


def debug_vertical_alignment(
    base_before: TTFont,
    donor: TTFont,
    merged: TTFont,
    codepoints: list[int],
) -> None:
    """
    Compare selected glyph bounds across base, donor, and merged fonts.
    """
    base_cmap = get_best_cmap(base_before)
    donor_cmap = get_best_cmap(donor)
    merged_cmap = get_best_cmap(merged)

    log.info("Vertical alignment diagnostic for selected glyphs:")
    log_vertical_metrics(base_before, "  Base")
    log_vertical_metrics(donor, "  Donor")
    log_vertical_metrics(merged, "  Merged")

    for cp in codepoints:
        char = chr(cp)
        tag = f"U+{cp:04X} {repr(char)}"

        base_name = base_cmap.get(cp)
        donor_name = donor_cmap.get(cp)
        merged_name = merged_cmap.get(cp)

        if base_name:
            base_bounds = get_glyph_bounds(base_before, base_name)
        else:
            base_bounds = (None, None)
        if donor_name:
            donor_bounds = get_glyph_bounds(donor, donor_name)
        else:
            donor_bounds = (None, None)
        if merged_name:
            merged_bounds = get_glyph_bounds(merged, merged_name)
        else:
            merged_bounds = (None, None)

        log.info(
            "  %s: base=%s %s donor=%s %s merged=%s %s",
            tag,
            base_name or "-",
            base_bounds,
            donor_name or "-",
            donor_bounds,
            merged_name or "-",
            merged_bounds,
        )


def copy_glyph(
    src_font: TTFont, dst_font: TTFont, src_name: str, dst_name: str
) -> None:
    """
    Deep-copy a glyph from src_font into dst_font.

    Handles composite glyphs recursively: if the glyph references component glyphs
    (e.g., 'Aacute' references 'A' and 'acutecomb'), those components are also copied.
    Components are namespaced with dst_name prefix to avoid collisions.

    Copies: glyf table entry (outlines) + hmtx table entry (advance width + LSB).

    Glyph-level TrueType instructions are stripped from transplanted glyphs.
    The merged font keeps the base font's global hinting tables, so donor
    glyph programs would otherwise execute against an incompatible CVT/FDEF/PREP
    environment and can rasterize with visible artifacts.
    """
    src_glyf = src_font["glyf"]
    dst_glyf = dst_font["glyf"]
    src_hmtx = src_font["hmtx"]
    dst_hmtx = dst_font["hmtx"]

    if dst_name in dst_glyf.glyphs:
        return  # Already copied (composite deduplication)

    src_glyph = src_glyf[src_name]

    # For composite glyphs, recursively copy each component first
    if hasattr(src_glyph, "components") and src_glyph.components:
        src_glyph = copy.deepcopy(src_glyph)
        for component in src_glyph.components:
            comp_src = component.glyphName
            comp_dst = f"_ens_{comp_src}"
            copy_glyph(src_font, dst_font, comp_src, comp_dst)
            component.glyphName = comp_dst
        src_glyph.removeHinting()
        dst_glyf[dst_name] = src_glyph  # already a detached copy
    else:
        copied = copy.deepcopy(src_glyph)
        copied.removeHinting()
        dst_glyf[dst_name] = copied
    dst_hmtx.metrics[dst_name] = copy.deepcopy(src_hmtx.metrics[src_name])


def update_cmap(font: TTFont, codepoint: int, glyph_name: str) -> None:
    """Update Unicode cmap subtables to map codepoint -> glyph_name.

    cmap format 4 is BMP-only (U+0000-U+FFFF, stored as unsigned short).
    Non-BMP codepoints (>U+FFFF) must only go into format 12 (full Unicode).
    Writing them into format 4 causes an OverflowError on compile.
    """
    cmap_table = font["cmap"]
    bmp = codepoint <= 0xFFFF

    for subtable in cmap_table.tables:
        if subtable.platformID not in (0, 3):
            continue
        fmt = subtable.format
        if bmp and fmt in (4, 6):
            # BMP subtables: safe to write BMP codepoints
            subtable.cmap[codepoint] = glyph_name
        elif fmt in (12, 13):
            # Full Unicode subtables: write all codepoints
            subtable.cmap[codepoint] = glyph_name
        elif subtable.platformID == 0 and fmt in (3, 4) and bmp:
            subtable.cmap[codepoint] = glyph_name


def glyph_name_for_codepoint(codepoint: int, prefix: str) -> str:
    """Generate a deterministic, unique glyph name for a codepoint."""
    if codepoint <= 0xFFFF:
        return f"{prefix}uni{codepoint:04X}"
    return f"{prefix}u{codepoint:06X}"


def transplant_glyphs(
    src_font: TTFont,
    dst_font: TTFont,
    prefix: str,
) -> int:
    """
    Copy every codepoint from src_font into dst_font, overwriting any existing
    entry. Codepoints present only in dst_font (e.g. WenKai-exclusive CJK) are
    untouched because they simply don't appear in src_font's cmap.

    Args:
        src_font:  Source font (donor)
        dst_font:  Destination font (base, modified in-place)
        prefix:    Glyph name prefix for transplanted glyphs (e.g. "mes_")

    Returns:
        Count of glyphs successfully transplanted.
    """
    src_cmap = get_best_cmap(src_font)
    count = 0

    for cp, src_glyph_name in src_cmap.items():
        dst_glyph_name = glyph_name_for_codepoint(cp, prefix)
        try:
            copy_glyph(src_font, dst_font, src_glyph_name, dst_glyph_name)
            update_cmap(dst_font, cp, dst_glyph_name)
            count += 1
        except Exception as e:
            log.warning(f"  Could not copy U+{cp:04X} ({src_glyph_name}): {e}")

    return count


def fix_glyph_order(font: TTFont) -> None:
    """
    Rebuild the glyph order list to include all glyphs in the glyf table.
    fonttools requires glyph order to be consistent with glyf contents.
    """
    existing_order = font.getGlyphOrder()
    existing_set = set(existing_order)
    glyf_names = set(font["glyf"].keys())
    new_glyphs = sorted(g for g in glyf_names if g not in existing_set)
    if new_glyphs:
        log.info(f"Adding {len(new_glyphs)} new glyphs to glyph order")
        font.setGlyphOrder(existing_order + new_glyphs)


def check_upm_compatibility(base: TTFont, donor: TTFont) -> None:
    """
    Check that both fonts share the same unitsPerEm value.
    If they differ, scale the donor font to match the base.
    This MUST be done before any glyph transplantation.
    """
    base_upm = base["head"].unitsPerEm
    donor_upm = donor["head"].unitsPerEm

    if base_upm == donor_upm:
        log.info(f"UPM match: {base_upm} units/em")
        return

    log.warning(
        f"UPM mismatch: base={base_upm}, donor={donor_upm}. "
        f"Scaling donor to {base_upm}..."
    )
    try:
        from fontTools.ttLib.scaleUpem import scale_upem

        scale_upem(donor, base_upm)
        log.info(f"Donor scaled to {base_upm} UPM successfully")
    except ImportError:
        # Older fonttools versions
        log.error(
            "fontTools.ttLib.scaleUpem not available. "
            "Please upgrade: pip install 'fonttools>=4.28.0'"
        )
        sys.exit(1)


def set_font_metadata(
    font: TTFont,
    family_name: str,
    ps_family: str,
    style: str,
    version: str,
    lxgw_ver: str,
    nerd_ver: str,
) -> None:
    """
    Set all name table entries for OFL compliance and correct font identification.

    OFL 1.1 compliance requires:
    - Do NOT use reserved names: "LXGW", "霞鶩", "Klee"
    - Our reserved names: "ENS Font", "Elegant Nerd Sino"

    Name IDs set:
      0  Copyright
      1  Font Family name
      2  Font Subfamily name (Regular/Bold/Italic/Bold Italic)
      3  Unique font identifier
      4  Full font name
      5  Version string
      6  PostScript name (no spaces, A-Za-z0-9- only)
      8  Manufacturer
      11 URL Vendor
      13 License description
      14 License URL
      16 Preferred/Typographic Family name (modern apps use this for family grouping)
      19 Sample text
    """
    name_table = font["name"]

    ps_style = style.replace(" ", "")
    full_name = f"{family_name} {style}"
    ps_name = f"{ps_family}-{ps_style}"
    version_str = f"Version {version}; lxgw{lxgw_ver}; nerd{nerd_ver}"
    unique_id = f"{version_str}; {ps_name}"

    copyright_notice = (
        "ENS Font (Elegant Nerd Sino) is a derivative work.\n"
        "CJK glyphs: LXGW WenKai / WenKai Mono (c) 2021 Xiaocheng Liao, SIL OFL 1.1\n"
        "Latin/ASCII glyphs: Meslo LG (c) 2009, 2010, 2013 Andre Berg, Apache License 2.0\n"
        "Nerd patch and PUA icons: Nerd Fonts (c) 2014 Ryan L McIntyre, MIT License\n"
        f"Compiled font: (c) {datetime.now().year} enstw (https://ens.tw/font), SIL OFL 1.1\n"
        'Reserved Font Names: "ENS Font" and "Elegant Nerd Sino".\n'
        'The names "LXGW", "霞鶩", and "Klee" are NOT used by this derivative.'
    )

    license_text = (
        "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
        "This license is available with a FAQ at: https://openfontlicense.org. "
        "ASCII/Latin glyphs derived from Meslo LG are used under the Apache License 2.0."
    )

    entries = [
        (0, copyright_notice),
        (1, family_name),
        (2, style),
        (3, unique_id),
        (4, full_name),
        (5, version_str),
        (6, ps_name),
        (8, "enstw"),
        (9, "ENSFont"),
        (11, "https://ens.tw/font"),
        (13, license_text),
        (14, "https://openfontlicense.org"),
        (16, family_name),
        (
            19,
            "ENS:  main  ⇡1 ⇣0  ✚2 ~1 -0  |  git commit -m '修正字型預覽'  ✓ ；Elegant Nerd Sino：English + 繁體中文 + 简体中文 + 日本語 + 한국어。",
        ),
    ]

    # Clear ALL name records to ensure no leftover "LXGW" or "霞鶩" names from WenKai base
    name_table.names = []

    # Write Unicode-capable records first to avoid '?' replacement in preview text.
    # Keep zh-TW first for better TC classification and keep en-US as fallback.
    for name_id, value in entries:
        for platform_id, enc_id, lang_id in [
            (0, 4, 0),  # Unicode 2.0+ (full repertoire)
            (3, 1, 0x0404),  # zh-TW (Windows)
            (3, 1, 0x0409),  # en-US (Windows fallback)
        ]:
            record = _n_a_m_e.NameRecord()
            record.nameID = name_id
            record.platformID = platform_id
            record.platEncID = enc_id
            record.langID = lang_id
            if platform_id in (0, 3):
                record.string = value.encode("utf-16-be")
            name_table.names.append(record)

    log.info(f"Font name set: {full_name} / PS: {ps_name}")


def set_os2_metrics(font: TTFont, meslo_ref: TTFont) -> None:
    """
    Set OS/2 and hhea metrics for terminal compatibility.

    Rule: Always use the donor font as the metric reference because it defines
    the rhythm that terminal emulators expect. WenKai's CJK characters will
    render double-width at the terminal level - this is correct behavior and
    does not require metric adjustment.

    Key rules for terminal compatibility:
      hhea.ascent  == OS/2.usWinAscent  == OS/2.sTypoAscender
      hhea.descent == -OS/2.usWinDescent (sign flipped) == OS/2.sTypoDescender
      These three must be consistent or some terminals clip/overlap lines.

    Setting fsSelection bit 7 (USE_TYPO_METRICS) tells apps to use
    sTypo* values instead of usWin* values (modern behavior).
    """
    os2 = font["OS/2"]
    hhea = font["hhea"]
    ref_os2 = meslo_ref["OS/2"]
    ref_hhea = meslo_ref["hhea"]

    # Typographic metrics (used by modern apps with USE_TYPO_METRICS)
    os2.sTypoAscender = ref_os2.sTypoAscender
    os2.sTypoDescender = ref_os2.sTypoDescender
    os2.sTypoLineGap = ref_os2.sTypoLineGap

    # Win metrics (used by legacy GDI on Windows)
    os2.usWinAscent = ref_os2.usWinAscent
    os2.usWinDescent = ref_os2.usWinDescent

    # hhea must match for cross-platform consistency
    hhea.ascent = ref_hhea.ascent
    hhea.descent = ref_hhea.descent
    hhea.lineGap = ref_hhea.lineGap

    # Set USE_TYPO_METRICS (bit 7 of fsSelection)
    os2.fsSelection |= 0x80

    # fsType = 0: installable embedding (required by OFL)
    os2.fsType = 0

    # Text metrics from the Meslo donor for correct rendering hints
    os2.sxHeight = ref_os2.sxHeight
    os2.sCapHeight = ref_os2.sCapHeight

    # Merge Unicode range bits: OR together both fonts' declared ranges
    os2.ulUnicodeRange1 = ref_os2.ulUnicodeRange1 | font["OS/2"].ulUnicodeRange1
    os2.ulUnicodeRange2 = ref_os2.ulUnicodeRange2 | font["OS/2"].ulUnicodeRange2
    os2.ulUnicodeRange3 = ref_os2.ulUnicodeRange3 | font["OS/2"].ulUnicodeRange3
    os2.ulUnicodeRange4 = ref_os2.ulUnicodeRange4 | font["OS/2"].ulUnicodeRange4

    log.info(
        f"OS/2 metrics: ascender={os2.sTypoAscender}, "
        f"descender={os2.sTypoDescender}, lineGap={os2.sTypoLineGap}"
    )


def assert_donor_is_mono(donor: TTFont, donor_path: str) -> None:
    """
    Assert that the donor font is monospaced (post.isFixedPitch == 1).
    Called before transplant for --mono builds to prevent accidentally wiring
    a proportional font as a mono donor.
    Exits with error if the check fails.
    """
    if donor["post"].isFixedPitch != 1:
        log.error(
            f"Donor font is NOT monospaced (post.isFixedPitch != 1): {donor_path}\n"
            "  A monospaced donor is required for --mono builds.\n"
            "  Use a Meslo LGSDZ Nerd Font Mono donor for --mono builds."
        )
        sys.exit(1)
    log.info(f"Donor mono check: PASS (post.isFixedPitch=1): {donor_path}")


def _shift_glyph_x(font: TTFont, gname: str, dx: int) -> None:
    """Translate all x-coordinates of a glyf glyph by dx units."""
    glyf_table = font["glyf"]
    g = glyf_table[gname]
    if g.numberOfContours == 0:
        return
    if g.numberOfContours > 0:
        # Simple glyph: shift all coordinate x values
        for i, (x, y) in enumerate(g.coordinates):
            g.coordinates[i] = (x + dx, y)
    elif g.numberOfContours == -1:
        # Composite glyph: shift component offsets
        for comp in g.components:
            comp.x += dx
    g.recalcBounds(glyf_table)


def normalize_half_widths(font: TTFont, cell_width: int) -> None:
    """
    After transplant, enforce a cell_width-aligned advance grid.

    WenKai Mono TC uses a 500/1000 grid (half/full), but ENSFontMono uses a
    600/1200 grid. Three passes:
      1. Sub-half-cell  (0 < adv < cell_width):         bump to cell_width   (500→600)
      2. Between half/full (cell_width < adv < 2*cell_width): snap by midpoint
         so near-half widths stay half-width (602→600) while true full-width
         WenKai glyphs still expand to full-width (1000→1200)
      3. Over-full-cell (adv > 2*cell_width):            round up to nearest multiple
                                                         of 2*cell_width (2000→2400, 3000→3600)
    Combining marks (advance=0) and correctly-sized glyphs are untouched.

    When advance width increases, glyph outlines are shifted right by half the
    difference so spacing is distributed evenly on both sides.
    """
    import math
    hmtx = font["hmtx"]
    full_width = 2 * cell_width
    half_to_full_midpoint = (cell_width + full_width) / 2
    half_corrected = 0
    full_corrected = 0
    over_corrected = 0
    for gname, (adv, lsb) in list(hmtx.metrics.items()):
        if 0 < adv < cell_width:
            dx = (cell_width - adv) // 2
            new_lsb = lsb + dx
            log.debug(f"  normalize half: {gname} {adv} -> {cell_width} (lsb {lsb} -> {new_lsb})")
            _shift_glyph_x(font, gname, dx)
            hmtx.metrics[gname] = (cell_width, new_lsb)
            half_corrected += 1
        elif cell_width < adv < full_width:
            target_width = cell_width if adv < half_to_full_midpoint else full_width
            dx = (target_width - adv) // 2
            new_lsb = lsb + dx
            log.debug(
                f"  normalize mid: {gname} {adv} -> {target_width} "
                f"(lsb {lsb} -> {new_lsb})"
            )
            _shift_glyph_x(font, gname, dx)
            hmtx.metrics[gname] = (target_width, new_lsb)
            if target_width == cell_width:
                half_corrected += 1
            else:
                full_corrected += 1
        elif adv > full_width:
            rounded = math.ceil(adv / full_width) * full_width
            dx = (rounded - adv) // 2
            new_lsb = lsb + dx
            log.debug(f"  normalize over: {gname} {adv} -> {rounded} (lsb {lsb} -> {new_lsb})")
            _shift_glyph_x(font, gname, dx)
            hmtx.metrics[gname] = (rounded, new_lsb)
            over_corrected += 1
    log.info(
        f"  normalize_half_widths: {half_corrected} glyphs -> {cell_width}, "
        f"{full_corrected} glyphs -> {full_width}, "
        f"{over_corrected} glyphs rounded to cell-aligned multiple"
    )


def compute_x_avg_char_width(font: TTFont) -> int:
    """
    Compute xAvgCharWidth using the OpenType spec weighted formula.
    Weights: 26 lowercase a-z + space, standard OpenType frequency weights (total 1000).
    Must be called after normalize_half_widths() so advance widths are already corrected.
    """
    cmap = get_best_cmap(font)
    hmtx = font["hmtx"]

    # OpenType spec weights (sum = 1000)
    weights = {
        'a': 64, 'b': 14, 'c': 27, 'd': 35, 'e': 100, 'f': 20, 'g': 14,
        'h': 42, 'i': 63, 'j':  3, 'k':  6, 'l': 35, 'm':  20, 'n': 56,
        'o': 56, 'p': 17, 'q':  4, 'r': 49, 's': 56, 't':  71, 'u': 31,
        'v': 10, 'w': 18, 'x':  3, 'y': 18, 'z':  2, ' ': 166,
    }

    total_weight = 0
    weighted_sum = 0
    for char, weight in weights.items():
        cp = ord(char)
        if cp in cmap:
            gname = cmap[cp]
            if gname in hmtx.metrics:
                weighted_sum += hmtx.metrics[gname][0] * weight
                total_weight += weight

    if total_weight == 0:
        log.warning("compute_x_avg_char_width: no weighted glyphs found, keeping existing value")
        return font["OS/2"].xAvgCharWidth

    return round(weighted_sum / total_weight)


def validate_monospace_integrity(font: TTFont, is_mono: bool = False) -> None:
    """
    Verify half-width glyphs have the expected uniform advance width.

    For mono builds: checks ASCII + Latin Extended-A/B + Greek & Coptic + Cyrillic
    + Greek Extended + Nerd PUA BMP. Emits log.error + sys.exit(1) on any violation.

    For non-mono builds: checks ASCII only, issues a warning (not error).
    """
    cmap = get_best_cmap(font)
    hmtx = font["hmtx"]

    # Determine cell width from ASCII printable range
    ascii_widths = set()
    for cp in range(0x0020, 0x007F):
        if cp in cmap:
            gname = cmap[cp]
            if gname in hmtx.metrics:
                ascii_widths.add(hmtx.metrics[gname][0])

    if not ascii_widths:
        log.warning("No ASCII glyphs found - cannot verify monospace integrity")
        return

    if len(ascii_widths) > 1:
        msg = (
            f"ASCII glyphs have {len(ascii_widths)} different advance widths: "
            f"{sorted(ascii_widths)}."
        )
        if is_mono:
            log.error(f"MONOSPACE INTEGRITY FAIL: {msg}")
            sys.exit(1)
        else:
            log.warning(f"MONOSPACE INTEGRITY: {msg} Expected for non-mono builds.")
            return

    cell_width = ascii_widths.pop()
    log.info(f"Monospace integrity: ASCII cell width = {cell_width} units")

    if not is_mono:
        log.info("Monospace integrity OK (ASCII-only check for non-mono build)")
        return

    # Extended check for mono builds
    extended_ranges = [
        (0x0100, 0x024F, "Latin Extended-A/B"),
        (0x0370, 0x03FF, "Greek & Coptic"),
        (0x0400, 0x04FF, "Cyrillic"),
        (0x1F00, 0x1FFF, "Greek Extended"),
        (0xE000, 0xF8FF, "Nerd PUA BMP"),
    ]

    violations = []
    for start, end, block_name in extended_ranges:
        for cp in range(start, end + 1):
            if cp in cmap:
                gname = cmap[cp]
                if gname in hmtx.metrics:
                    adv = hmtx.metrics[gname][0]
                    if adv != 0 and adv % cell_width != 0:
                        violations.append((cp, adv, block_name))

    if violations:
        log.error(
            f"MONOSPACE INTEGRITY FAIL: {len(violations)} glyphs with wrong advance "
            f"width (expected {cell_width}):"
        )
        for cp, adv, block_name in violations[:10]:
            log.error(f"  U+{cp:04X} in {block_name}: advance={adv}")
        if len(violations) > 10:
            log.error(f"  ... and {len(violations) - 10} more")
        sys.exit(1)

    log.info(
        f"Monospace integrity OK: all checked glyphs at {cell_width} units "
        f"(ASCII + extended ranges)"
    )


def set_monospaced_metadata(font: TTFont, is_mono: bool) -> None:
    """
    Set metadata flags that tell terminal emulators this is a monospaced font.
    - post.isFixedPitch: 1 for mono, 0 for proportional
    - OS/2.panose.bProportion: 9 for mono, 0 (any) or 2 (proportional)
    - OS/2.panose.bSerifStyle: 0 (Any) — inherited from WenKai base as 2 (Cove),
      which incorrectly classifies this sans-serif font as serifed. Reset to 0 to
      match the donor family and avoid wrong font-substitution matches.
    - OS/2.xAvgCharWidth: Set to width of 'h' (approximate)
    - OS/2.achVendID: Set to 'ENSF' (ENS Font)
    """
    post = font["post"]
    os2 = font["OS/2"]

    # Set Vendor ID (4-character tag)
    os2.achVendID = "ENSF"

    # bSerifStyle=2 (Cove) is inherited from WenKai and is wrong for a sans-serif font.
    # Set to 0 (Any) to avoid incorrect serif font substitution.
    os2.panose.bSerifStyle = 0

    if is_mono:
        log.info("Setting monospaced flags (isFixedPitch=1, Panose=9)")
        post.isFixedPitch = 1
        os2.panose.bProportion = 9
    else:
        log.info("Setting proportional flags (isFixedPitch=0, Panose=2)")
        post.isFixedPitch = 0
        if os2.panose.bProportion == 9:
            os2.panose.bProportion = 2


def fix_block_elements(font: TTFont) -> None:
    """
    Rescale block element glyphs (U+2580-U+259F) so they fill the font's actual
    ascent-to-descent cell.

    Background: the Nerd Fonts patcher increases Meslo's hhea.ascent from ~1576 to
    2001 (in 2048 UPM) to accommodate tall icon glyphs, but does NOT update the
    block element outlines.  After UPM scaling to 1000, the FULL BLOCK ends up with
    yMax=770 while hhea.ascent=977 — a 207-unit gap at the top.  Meslo ships a
    hinting program on each block element that snaps it to fill the cell at render
    time, but copy_glyph strips all donor hinting (removeHinting) because it
    references Meslo's FDEF/CVT tables which are absent from the merged font.

    Fix: use the FULL BLOCK glyph's raw bounding box as the "design cell" (the
    original pre-NF-patch ascent/descent) and proportionally rescale every block
    element glyph's y-coordinates from [design_yMin, design_yMax] to
    [hhea.descent, hhea.ascent].

    Must be called after set_os2_metrics() so the final metrics are in place.
    Only y-coordinates are touched; x-coordinates are preserved so the
    intentional ±bleed at horizontal cell edges continues to tile correctly.
    """
    cmap = get_best_cmap(font)
    if 0x2588 not in cmap:
        log.warning("fix_block_elements: U+2588 FULL BLOCK not in cmap — skipping")
        return

    glyf_table = font["glyf"]
    fb_name = cmap[0x2588]
    design_desc, design_asc = get_glyph_bounds(font, fb_name)
    if design_desc is None or design_asc is None:
        log.warning("fix_block_elements: FULL BLOCK bounds unavailable — skipping")
        return
    design_cell = design_asc - design_desc

    font_asc = font["hhea"].ascent
    font_desc = font["hhea"].descent
    font_cell = font_asc - font_desc

    if design_cell == 0:
        log.warning("fix_block_elements: FULL BLOCK has zero height — skipping")
        return

    if design_asc == font_asc and design_desc == font_desc:
        log.info("fix_block_elements: block elements already match font metrics — nothing to do")
        return

    log.info(
        f"fix_block_elements: rescaling y from design cell [{design_desc}, {design_asc}] "
        f"to font cell [{font_desc}, {font_asc}]"
    )

    fixed = 0
    seen: set[str] = set()
    for cp in range(0x2580, 0x25A0):  # Block Elements
        if cp not in cmap:
            continue
        gname = cmap[cp]
        if gname in seen:
            continue
        seen.add(gname)
        g = glyf_table[gname]
        if g.numberOfContours <= 0:
            continue
        for i, (x, y) in enumerate(g.coordinates):
            new_y = round(font_desc + (y - design_desc) / design_cell * font_cell)
            g.coordinates[i] = (x, new_y)
        g.recalcBounds(glyf_table)
        fixed += 1

    log.info(f"fix_block_elements: rescaled {fixed} glyphs")


def rebuild_vmtx(font: TTFont) -> None:
    """
    Rebuild the vmtx table so every glyph in the font has a valid entry.

    After glyph transplantation the glyph count grows but vmtx still holds
    only the original WenKai entries, making the table corrupt (too short).

    Strategy (matches WenKai's own approach):
      - advance height = vhea.advanceHeightMax  (uniform for all glyphs)
      - tsb            = vhea.ascent - glyph.yMax
                         (0 for composite / empty glyphs)
    """
    vhea = font["vhea"]
    adv_height = vhea.advanceHeightMax
    vert_ascent = vhea.ascent  # top of the em square in vertical coordinates

    glyf_table = font["glyf"]
    existing = font["vmtx"].metrics  # dict: glyph_name -> (advanceHeight, tsb)

    glyph_order = font.getGlyphOrder()
    rebuilt = 0
    for name in glyph_order:
        if name in existing:
            continue  # already has an entry; keep it
        # Compute tsb from bounding box if glyph has outlines
        tsb = 0
        try:
            g = glyf_table[name]
            if g.numberOfContours != 0:  # not empty / not composite with no bbox
                g.recalcBounds(glyf_table)
                if hasattr(g, "yMax") and g.yMax is not None:
                    tsb = vert_ascent - g.yMax
        except Exception as e:
            log.debug(f"  vmtx: could not compute tsb for '{name}': {e}")
        existing[name] = (adv_height, tsb)
        rebuilt += 1

    # numberOfVMetrics=1 means only 1 full entry; the rest repeat the last
    # advance value.  Set it to total glyph count so every entry is explicit,
    # which avoids any ambiguity and satisfies macOS validation.
    vhea.numberOfVMetrics = len(glyph_order)
    log.info(
        f"  vmtx rebuilt: {rebuilt} new entries added, "
        f"total {len(glyph_order)} (advanceHeight={adv_height})"
    )


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
    normalize_half_widths(base, cell_width)

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
    log.info(f"Setting {'monospaced' if is_mono else 'proportional'} metadata...")
    set_monospaced_metadata(base, is_mono)

    # Set xAvgCharWidth using the OpenType spec weighted formula.
    # Done after normalize_half_widths so widths are already corrected.
    avg_w = compute_x_avg_char_width(base)
    base["OS/2"].xAvgCharWidth = avg_w
    log.info(f"  xAvgCharWidth set to {avg_w} (OpenType weighted formula)")

    # Validate monospace integrity
    if is_mono:
        log.info("Validating monospace integrity (extended ranges)...")
        validate_monospace_integrity(base, is_mono=True)
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
        debug_vertical_cps=debug_vertical_cps,
    )


if __name__ == "__main__":
    main()
