import logging
import copy
from fontTools.ttLib import TTFont
from .cmap import get_best_cmap, update_cmap, glyph_name_for_codepoint
from .metrics import get_glyph_bounds

log = logging.getLogger(__name__)

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
        src_glyph_copy = copy.deepcopy(src_glyph)
        for component in src_glyph_copy.components:
            comp_src = component.glyphName
            comp_dst = f"_ens_{comp_src}"
            copy_glyph(src_font, dst_font, comp_src, comp_dst)
            component.glyphName = comp_dst
        src_glyph_copy.removeHinting()
        dst_glyf[dst_name] = src_glyph_copy  # already a detached copy
    else:
        copied = copy.deepcopy(src_glyph)
        copied.removeHinting()
        dst_glyf[dst_name] = copied
    dst_hmtx.metrics[dst_name] = list(src_hmtx.metrics[src_name])


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


def normalize_half_widths(font: TTFont, cell_width: int, is_mono_prop: bool = False) -> None:
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

    If is_mono_prop is True, we skip normalization for Nerd Font icons in PUA
    (U+E000-U+F8FF and Plane 15 U+F0000-U+FFFFF) to allow them to be proportional.
    """
    import math
    hmtx = font["hmtx"]
    cmap = get_best_cmap(font)
    rev_cmap = {v: k for k, v in cmap.items()}

    full_width = 2 * cell_width
    half_to_full_midpoint = (cell_width + full_width) / 2
    half_corrected = 0
    full_corrected = 0
    over_corrected = 0
    skipped_prop = 0

    for gname, (adv, lsb) in list(hmtx.metrics.items()):
        if adv == 0:
            continue

        # Skip normalization for Nerd Font icons if in mono-prop mode
        if is_mono_prop and gname in rev_cmap:
            cp = rev_cmap[gname]
            if (0xE000 <= cp <= 0xF8FF) or (0xF0000 <= cp <= 0xFFFFF):
                skipped_prop += 1
                continue

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

    msg = (
        f"  normalize_half_widths: {half_corrected} glyphs -> {cell_width}, "
        f"{full_corrected} glyphs -> {full_width}, "
        f"{over_corrected} glyphs rounded to cell-aligned multiple"
    )
    if skipped_prop > 0:
        msg += f" (skipped {skipped_prop} Nerd icons for mono-prop)"
    log.info(msg)


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
