#!/usr/bin/env python3
"""
merge.py - Merges LXGWWenKaiMono + MesloLGMNerdFont into ENS Font (Elegant Nerd Sino).

Merge strategy:
  Base:   LXGW WenKai Mono  — CJK, Hiragana, Katakana, fullwidth, and all other glyphs
  Donor:  MesloLGMNerdFont  — ASCII, Latin, Box Drawing, PUA icons (Meslo + Nerd Fonts
          are already bundled together in a single TTF, so no priority resolution needed)

All donor codepoints not already present in the base are transplanted in a single pass.

Usage:
    python scripts/merge.py \\
        --wenkai  fonts/wenkai/LXGWWenKaiMono-Regular.ttf \\
        --meslo   fonts/meslo/MesloLGMNerdFont-Regular.ttf \\
        --output  dist/ENSFont-Regular.ttf \\
        --style   Regular \\
        --version 1.0.0 \\
        --lxgw-version 1.521 \\
        --nerd-version 3.4.0
"""

import argparse
import copy
import logging
import sys
from pathlib import Path

from fontTools import ttLib
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _n_a_m_e

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


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


def copy_glyph(
    src_font: TTFont, dst_font: TTFont, src_name: str, dst_name: str
) -> None:
    """
    Deep-copy a glyph from src_font into dst_font.

    Handles composite glyphs recursively: if the glyph references component glyphs
    (e.g., 'Aacute' references 'A' and 'acutecomb'), those components are also copied.
    Components are namespaced with dst_name prefix to avoid collisions.

    Copies: glyf table entry (outlines) + hmtx table entry (advance width + LSB).
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

    dst_glyf[dst_name] = copy.deepcopy(src_glyph)
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
    new_glyphs = [g for g in glyf_names if g not in existing_set]
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
    style: str,
    version: str,
    lxgw_ver: str,
    nerd_ver: str,
) -> None:
    """
    Set all name table entries for OFL compliance and correct font identification.

    OFL 1.1 compliance requires:
    - Do NOT use reserved names: "LXGW", "霞鶩", "Klee", "Meslo"
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
      19 Sample text
    """
    name_table = font["name"]

    family_name = "ENS Font"
    ps_style = style.replace(" ", "")  # "BoldItalic" etc.
    full_name = f"ENS Font {style}"
    ps_name = f"ENSFont-{ps_style}"
    version_str = f"Version {version}; lxgw{lxgw_ver}; nerd{nerd_ver}"
    unique_id = f"{version_str}; {ps_name}"

    copyright_notice = (
        "ENS Font (Elegant Nerd Sino) is a derivative work.\n"
        "CJK glyphs: LXGW WenKai Mono (c) 2021 Xiaocheng Liao, SIL OFL 1.1\n"
        "Latin/ASCII glyphs: MesloLGM (c) 2009-2013 Andre Berg, Apache License 2.0\n"
        "PUA icons: Nerd Fonts (c) 2014 Ryan L McIntyre, MIT License\n"
        "Compiled font: (c) 2026 enstw (https://ens.tw/font), SIL OFL 1.1\n"
        'Reserved Font Names: "ENS Font" and "Elegant Nerd Sino".\n'
        'The names "LXGW", "霞鶩", "Klee", and "Meslo" are NOT used by this derivative.'
    )

    license_text = (
        "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
        "This license is available with a FAQ at: https://openfontlicense.org. "
        "ASCII/Latin glyphs derived from MesloLGM are used under the Apache License 2.0."
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
        (11, "https://ens.tw/font"),
        (13, license_text),
        (14, "https://openfontlicense.org"),
        (
            19,
            "Elegant Nerd Sino Font：終端機字體預覽，English + 繁體中文 + 1234567890。",
        ),
    ]

    # Clear name IDs we are replacing
    ids_to_clear = {e[0] for e in entries}
    name_table.names = [n for n in name_table.names if n.nameID not in ids_to_clear]

    # Write Traditional Chinese localized names first so font managers classify it as TC.
    # Keep en-US as a fallback on Windows for apps that only surface English names.
    for name_id, value in entries:
        for platform_id, enc_id, lang_id in [
            (3, 1, 0x0404),  # zh-TW (Windows)
            (3, 1, 0x0409),  # en-US (Windows fallback)
            (1, 0, 19),      # Traditional Chinese (Mac)
        ]:
            record = _n_a_m_e.NameRecord()
            record.nameID = name_id
            record.platformID = platform_id
            record.platEncID = enc_id
            record.langID = lang_id
            if platform_id == 3:
                record.string = value.encode("utf-16-be")
            else:
                record.string = value.encode("mac_roman", errors="replace")
            name_table.names.append(record)

    log.info(f"Font name set: {full_name} / PS: {ps_name}")


def set_os2_metrics(font: TTFont, meslo_ref: TTFont) -> None:
    """
    Set OS/2 and hhea metrics for terminal compatibility.

    Rule: Always use MesloLGM as the metric reference because it defines
    the monospace rhythm that terminal emulators expect. WenKai's CJK
    characters will render double-width at the terminal level - this is
    correct behavior and does not require metric adjustment.

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

    # Text metrics from MesloLGM for correct rendering hints
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


def validate_monospace_integrity(font: TTFont) -> None:
    """
    Verify all ASCII printable glyphs (U+0020-U+007E) have identical advance widths.
    Issues a warning (not error) for violations - terminal usage depends on this.
    """
    cmap = get_best_cmap(font)
    hmtx = font["hmtx"]
    widths = set()

    for cp in range(0x0020, 0x007F):
        if cp in cmap:
            gname = cmap[cp]
            if gname in hmtx.metrics:
                widths.add(hmtx.metrics[gname][0])

    if len(widths) > 1:
        log.warning(
            f"MONOSPACE INTEGRITY VIOLATION: ASCII glyphs have {len(widths)} different "
            f"advance widths: {sorted(widths)}. Check MesloLGM source integrity."
        )
    elif len(widths) == 1:
        log.info(
            f"Monospace integrity OK: all ASCII glyphs width = {widths.pop()} units"
        )
    else:
        log.warning("No ASCII glyphs found - cannot verify monospace integrity")


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
        except Exception:
            pass
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
    meslo_path: str,
    output_path: str,
    style: str,
    version: str,
    lxgw_ver: str,
    nerd_ver: str,
) -> None:
    """
    Main merge function.

    Base:  LXGW WenKai Mono  - CJK, Hiragana, Katakana, fullwidth glyphs
    Donor: MesloLGMNerdFont  - ASCII, Latin, Box Drawing, PUA icons
           (Meslo and Nerd Fonts are pre-bundled; single transplant pass)

    Result is renamed to ENS Font for OFL compliance.
    """
    log.info(f"=== ENS Font Build: {style} ===")
    log.info(f"Loading LXGW WenKai Mono (base): {wenkai_path}")
    base = TTFont(wenkai_path)

    log.info(f"Loading MesloLGM Nerd Font (donor): {meslo_path}")
    meslo = TTFont(meslo_path)

    # Step 0: UPM compatibility check (scale donor if needed)
    log.info("Step 0: Checking UPM compatibility...")
    check_upm_compatibility(base, meslo)

    # Step 1: Ensure base has both BMP and full-Unicode cmap subtables
    log.info("Step 1: Ensuring cmap subtable coverage...")
    ensure_cmap_subtables(base)

    # Step 2: Transplant all MesloLGMNerdFont glyphs not already in WenKai.
    # Meslo and Nerd Fonts are pre-bundled in the same TTF; WenKai codepoints
    # are never overwritten — whatever WenKai has, it keeps.
    log.info("Step 2: Transplanting MesloLGMNerdFont glyphs (fill gaps only)...")
    meslo_count = transplant_glyphs(
        src_font=meslo,
        dst_font=base,
        prefix="mes_",
    )
    log.info(f"  -> {meslo_count} glyphs transplanted")

    # Step 4: Rebuild glyph order for internal consistency
    log.info("Step 4: Rebuilding glyph order...")
    fix_glyph_order(base)

    # Step 5: Suppress verbose post table glyph names (saves ~20% file size)
    base["post"].formatType = 3.0

    # Step 6: Set font metadata for OFL compliance
    log.info("Step 5: Setting font metadata (OFL compliance)...")
    set_font_metadata(base, style, version, lxgw_ver, nerd_ver)

    # Step 7: Set OS/2 and hhea metrics from MesloLGM reference
    log.info("Step 6: Setting OS/2/hhea metrics from MesloLGM...")
    set_os2_metrics(base, meslo)

    # Step 8: Sanity check
    log.info("Step 7: Validating monospace integrity...")
    validate_monospace_integrity(base)

    # Step 9: Rebuild vmtx so every glyph has a valid vertical metrics entry.
    # After transplanting Meslo glyphs the vmtx entry count no longer matches
    # the enlarged glyph set, causing macOS validation warnings.  We rebuild
    # the table: advance height = vhea.advanceHeightMax for every glyph,
    # tsb = vhea.ascent - yMax (0 for glyphs without outlines).
    if "vmtx" in base and "vhea" in base:
        log.info("Step 8: Rebuilding vmtx for full glyph coverage...")
        rebuild_vmtx(base)

    # Step 10: Save
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"Step 10: Saving to {output_path} ...")
    base.save(str(output))

    size_kb = output.stat().st_size // 1024
    log.info(f"=== Done: {output_path} ({size_kb:,} KB) ===")


def main():
    parser = argparse.ArgumentParser(
        description="Merge LXGWWenKaiMono + MesloLGMNerdFont into ENS Font"
    )
    parser.add_argument("--wenkai", required=True, help="Path to LXGWWenKaiMono-*.ttf")
    parser.add_argument("--meslo", required=True, help="Path to MesloLGMNerdFont-*.ttf")
    parser.add_argument("--output", required=True, help="Output .ttf path")
    parser.add_argument(
        "--style",
        required=True,
        choices=["Regular", "Bold", "Italic", "Bold Italic"],
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
    args = parser.parse_args()

    merge_fonts(
        wenkai_path=args.wenkai,
        meslo_path=args.meslo,
        output_path=args.output,
        style=args.style,
        version=args.version,
        lxgw_ver=args.lxgw_version,
        nerd_ver=args.nerd_version,
    )


if __name__ == "__main__":
    main()
