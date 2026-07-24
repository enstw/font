import logging
import copy
from fontTools.ttLib import TTFont
from .cmap import get_best_cmap, update_cmap, glyph_name_for_codepoint
from .metrics import get_glyph_bounds

log = logging.getLogger(__name__)

def copy_glyph(
    src_font: TTFont, dst_font: TTFont, src_name: str, dst_name: str,
    prefix: str = "ens_",
) -> None:
    """
    Deep-copy a glyph from src_font into dst_font.

    Handles composite glyphs recursively: if the glyph references component glyphs
    (e.g., 'Aacute' references 'A' and 'acutecomb'), those components are also copied.
    Components are namespaced per donor prefix — two donors can both carry a
    component named 'period' without silently sharing one outline.

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
            comp_dst = f"_{prefix}{comp_src}"
            copy_glyph(src_font, dst_font, comp_src, comp_dst, prefix)
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
            copy_glyph(src_font, dst_font, src_glyph_name, dst_glyph_name, prefix)
            update_cmap(dst_font, cp, dst_glyph_name)
            count += 1
        except Exception as e:
            log.warning(f"  Could not copy U+{cp:04X} ({src_glyph_name}): {e}")

    return count


# Powerline separator glyphs (E0B0+ dividers and Powerline-extra shapes) must
# fill the terminal cell edge-to-edge / top-to-bottom so adjacent prompt
# segments join seamlessly. Shared by fit_nerd_icons (stretch) and
# fix_block_elements (edge snap).
POWERLINE_FILL_CPS = frozenset(list(range(0xE0B0, 0xE0D5)) + [0xE0D6, 0xE0D7])


def _transform_glyph(font: TTFont, gname: str, sx: float, sy: float, dx: float, dy: float) -> bool:
    """Apply x' = x*sx + dx, y' = y*sy + dy to a simple glyf glyph."""
    glyf_table = font["glyf"]
    g = glyf_table[gname]
    if g.numberOfContours <= 0:
        return False
    for i, (x, y) in enumerate(g.coordinates):
        g.coordinates[i] = (round(x * sx + dx), round(y * sy + dy))
    g.recalcBounds(glyf_table)
    return True


# Terminal-furniture codepoints for Mono / Mono Prop builds: characters that
# terminals allot ONE cell (wcwidth-narrow / East-Asian-ambiguous) but that the
# LXGW base draws CJK-style on the full em, so their ink overlaps the next
# cell in a terminal grid. Transplanted from a pinned monospaced text donor
# (Meslo, Bitstream Vera lineage — drawn for a terminal cell natively) and
# fitted to the base cell.
#
# Deliberately NOT included, so they keep LXGW's full-width CJK forms:
# ※ ‼ ①-⑳ ❶-➓ ⸺ ⸻ hexagrams and other enclosed/CJK-flavored symbols.
#
# Fill glyphs must tile edge-to-edge in both axes: x is fitted here, y is
# fix_block_elements' job (shared design-box -> line-box rescale + overshoot).
FURNITURE_FILL_CPS = frozenset(
    list(range(0x2500, 0x25A0)) +      # box drawing + block elements
    list(range(0x25E2, 0x25E6))        # ◢◣◤◥ cell-filling triangles
)
# Symbol glyphs keep their aspect ratio: uniform baseline-anchored scale.
FURNITURE_SYMBOL_CPS = frozenset(
    list(range(0x2190, 0x2200)) +      # arrows
    list(range(0x2200, 0x2300)) +      # mathematical operators
    list(range(0x25A0, 0x25E2)) +      # geometric shapes ■□▲●◆ ...
    list(range(0x25E6, 0x2600)) +      # ... minus the fill triangles
    [0x2010, 0x2014, 0x2015, 0x2016,   # ‐ — ― ‖
     0x2020, 0x2021, 0x2025, 0x2026,   # † ‡ ‥ …
     0x2027, 0x2030, 0x2031, 0x203F,   # ‧ ‰ ‱ ‿
     0x2713, 0x2714, 0x2717, 0x2718]   # ✓ ✔ ✗ ✘
)


def transplant_terminal_furniture(
    base: TTFont,
    donor: TTFont,
    cell_width: int,
    prefix: str = "fur_",
) -> int:
    """
    Transplant terminal-furniture glyphs from a monospaced text donor and fit
    them to the base cell. Mono / Mono Prop builds only.

    The donor must already be scaled to the base UPM (check_upm_compatibility).
    Its cell width is measured from 'M'. Two treatments:

      - FURNITURE_FILL_CPS: x-only map [0, donor_cell] -> [0, cell_width] so
        edges keep tiling seamlessly; vertical fit happens later in
        fix_block_elements (one shared transform for the whole range).
      - FURNITURE_SYMBOL_CPS: uniform baseline-anchored scale by
        cell_width / donor_cell, preserving the symbol's aspect ratio.
        Codepoints the base already draws at <= one cell keep the LXGW
        design; only full-width base glyphs are replaced.

    Codepoints missing from the donor are left untouched (they stay LXGW
    full-width — the rare-math tail).

    Returns the number of glyphs transplanted.
    """
    base_cmap = get_best_cmap(base)
    donor_cmap = get_best_cmap(donor)
    hmtx = base["hmtx"]
    glyf_table = base["glyf"]

    if 0x004D not in donor_cmap:
        log.warning("transplant_terminal_furniture: donor has no 'M' — skipping")
        return 0
    donor_cell = donor["hmtx"].metrics[donor_cmap[0x004D]][0]
    if donor_cell <= 0:
        log.warning("transplant_terminal_furniture: donor cell width unusable — skipping")
        return 0
    s = cell_width / donor_cell
    log.info(
        f"  furniture donor cell: {donor_cell} -> {cell_width} units (scale {s:.3f})"
    )

    count = 0
    for cp in sorted(FURNITURE_FILL_CPS | FURNITURE_SYMBOL_CPS):
        if cp not in donor_cmap:
            continue
        fill = cp in FURNITURE_FILL_CPS
        if not fill:
            base_gname = base_cmap.get(cp)
            if (
                base_gname
                and base_gname in hmtx.metrics
                and hmtx.metrics[base_gname][0] <= cell_width
            ):
                continue  # LXGW already draws it at one cell — keep the base design

        dst_name = glyph_name_for_codepoint(cp, prefix)
        try:
            copy_glyph(donor, base, donor_cmap[cp], dst_name, prefix)
            update_cmap(base, cp, dst_name)
        except Exception as e:
            log.warning(f"  Could not copy furniture U+{cp:04X}: {e}")
            continue

        g = glyf_table[dst_name]
        transformed = _transform_glyph(
            base, dst_name, s, 1.0 if fill else s, dx=0, dy=0
        )
        if not transformed and g.numberOfContours != 0:
            log.warning(
                f"  furniture U+{cp:04X} is not a simple glyph — advance pinned, outline untouched"
            )
        lsb = g.xMin if transformed else hmtx.metrics[dst_name][1]
        hmtx.metrics[dst_name] = (cell_width, lsb)
        count += 1

    log.info(f"  transplant_terminal_furniture: {count} glyphs fitted to {cell_width}-unit cell")
    return count


def fit_nerd_icons(
    font: TTFont,
    donor: TTFont,
    prefix: str = "don_",
    cell_width: int | None = None,
    fit_all: bool = False,
    icon_scale: float = 1.0,
) -> None:
    """
    Geometry pass for transplanted Nerd icon glyphs (every donor codepoint —
    the symbols-only donor carries icons exclusively, including a few outside
    PUA such as the IEC power symbols and the heavy angle brackets ❮❯).

    The Symbols Nerd Font donor is icon-only: its glyphs are drawn on the
    donor's own em/line box and are NOT pre-fitted to the base font's cell
    (that fitting used to be the Nerd Fonts patcher's job when the donor was
    a patched text font). Two treatments:

    1. Powerline separators (POWERLINE_FILL_CPS): stretched non-uniformly to
       fill the base line box [hhea.descent, hhea.ascent] vertically and the
       full advance horizontally. cell_width forces the advance to one cell
       (mono / mono-prop); None keeps each glyph's own advance (proportional).

    2. All other icons, when fit_all=True (strict mono): ONE shared affine
       transform scales the donor em down to cell_width and centers the donor
       line box in the base line box. A single transform (instead of
       per-glyph bbox fitting) preserves the icon set's internal relative
       alignment and sizing. Advance is pinned to cell_width.

    3. All other icons, when fit_all=False and icon_scale != 1.0 (Mono Prop
       and the proportional build): the same single shared transform, but
       with the given uniform scale and proportional advances (scaled, then
       normalize_half_widths snaps them to cell multiples for mono-prop).
       The symbols-only donor draws icons noticeably larger than the old
       patcher-fitted text donors did relative to LXGW's letterforms;
       icon_scale restores the icon-to-text proportion.

    Must run after check_upm_compatibility (donor already scaled to base UPM)
    and after transplant_glyphs, but before normalize_half_widths.
    """
    from .cmap import get_best_cmap

    cmap = get_best_cmap(font)
    glyf_table = font["glyf"]
    hmtx = font["hmtx"]

    base_asc = font["hhea"].ascent
    base_desc = font["hhea"].descent
    donor_asc = donor["hhea"].ascent
    donor_desc = donor["hhea"].descent
    upm = font["head"].unitsPerEm

    # Shared uniform transform for non-powerline icons: scale the donor em
    # (== base UPM after scaling) to the cell for strict mono, or by
    # icon_scale otherwise, then center the donor line box midpoint on the
    # base line box midpoint.
    s = (cell_width / upm) if (fit_all and cell_width) else icon_scale
    dy_center = (base_asc + base_desc) / 2 - ((donor_asc + donor_desc) / 2) * s

    stretched = 0
    fitted = 0
    scaled = 0
    seen: set[str] = set()

    for cp, gname in sorted(cmap.items()):
        if not gname.startswith(prefix) or gname in seen:
            continue
        seen.add(gname)
        g = glyf_table[gname]
        if g.numberOfContours <= 0:
            continue

        adv, _lsb = hmtx.metrics[gname]

        if cp in POWERLINE_FILL_CPS:
            g.recalcBounds(glyf_table)
            width = g.xMax - g.xMin
            height = g.yMax - g.yMin
            if width <= 0 or height <= 0:
                continue
            target_w = cell_width if cell_width else adv
            sx = target_w / width
            sy = (base_asc - base_desc) / height
            _transform_glyph(
                font, gname,
                sx, sy,
                dx=-g.xMin * sx,
                dy=base_desc - g.yMin * sy,
            )
            hmtx.metrics[gname] = (target_w, g.xMin)
            stretched += 1
        elif fit_all and cell_width:
            _transform_glyph(font, gname, s, s, dx=0, dy=dy_center)
            hmtx.metrics[gname] = (cell_width, g.xMin)
            fitted += 1
        elif icon_scale != 1.0:
            _transform_glyph(font, gname, s, s, dx=0, dy=dy_center)
            hmtx.metrics[gname] = (max(1, round(adv * icon_scale)), g.xMin)
            scaled += 1

    log.info(
        f"  fit_nerd_icons: {stretched} powerline glyphs stretched to line box"
        + (f", {fitted} icons fitted to {cell_width}-unit cell" if fit_all else "")
        + (f", {scaled} icons scaled by {icon_scale}" if scaled else "")
    )


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

    The ENS Font Mono grid is the LXGW native 500/1000 grid (half/full), so
    for base glyphs this is mostly a no-op; it exists to catch donor glyphs
    and base stragglers that land off-grid. Three passes:
      1. Sub-half-cell  (0 < adv < cell_width):         bump to cell_width
      2. Between half/full (cell_width < adv < 2*cell_width): snap by midpoint
         so near-half widths snap to half-width while near-full widths
         expand to full-width
      3. Over-full-cell (adv > 2*cell_width):            round up to nearest
                                                         multiple of 2*cell_width
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

        # For Nerd Font icons in mono-prop mode, snap to the nearest multiple of cell_width
        # instead of the standard half/full width rounding, allowing them to be >2 cells wide
        # but maintaining the exact multiples required by fontconfig for "Dual" spacing.
        is_pua_icon = False
        if is_mono_prop and gname in rev_cmap:
            cp = rev_cmap[gname]
            if (0xE000 <= cp <= 0xF8FF) or (0xF0000 <= cp <= 0xFFFFF):
                is_pua_icon = True

        if is_pua_icon:
            # Snap to nearest multiple of cell_width (>= 1)
            multiple = max(1, round(adv / cell_width))
            target_width = multiple * cell_width
            if adv != target_width:
                dx = (target_width - adv) // 2
                new_lsb = lsb + dx
                log.debug(f"  normalize PUA icon: {gname} {adv} -> {target_width} (lsb {lsb} -> {new_lsb})")
                _shift_glyph_x(font, gname, dx)
                hmtx.metrics[gname] = (target_width, new_lsb)
                skipped_prop += 1 # We use skipped_prop to count PUA icons processed for logging
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
        msg += f" (snapped {skipped_prop} Nerd icons to grid multiples for mono-prop)"
    log.info(msg)


def fix_block_elements(font: TTFont, overshoot_top: int = 75, overshoot_bot: int = -20) -> None:
    """
    Rescale block element and box drawing glyphs so they fill the font's actual
    cell, then apply overshoot to compensate for Terminal.app's extra cell padding.

    Phase 1 — Rescale:
    LXGW WenKai draws block elements and box drawing on its typographic design
    box (e.g. [-120, 880] in 1000 UPM), but terminal emulators size the cell
    from hhea/win metrics (e.g. [-241, 928]).  Without correction, stacked
    blocks and vertical box-drawing strokes show horizontal gaps between rows.
    Fix: proportionally rescale y-coordinates from the design cell (measured
    from the FULL BLOCK's raw bounds) to the font cell.  All affected glyphs
    share one linear transform, so box-drawing midlines and block boundaries
    keep meeting at the same y (the cell center) and junctions stay connected.

    Phase 2 — Overshoot:
    macOS Terminal.app allocates a pixel cell taller than the font's declared
    metrics (CoreText internal leading / rounding).  Empirical testing shows the
    actual cell extends ~75 units above ascent and the baseline is shifted ~20
    units down (so the bottom is 20 units higher than declared descent).
    Coordinates at the cell edges are snapped to overshoot targets so block
    elements fill Terminal.app's real cell.

    Args:
        overshoot_top:  units to extend above ascent (positive = upward)
        overshoot_bot:  units to extend below descent (negative = shrink upward)

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

    needs_rescale = not (design_asc == font_asc and design_desc == font_desc)

    if needs_rescale:
        log.info(
            f"fix_block_elements: rescaling y from design cell [{design_desc}, {design_asc}] "
            f"to font cell [{font_desc}, {font_asc}]"
        )

    overshoot_top_target = font_asc + overshoot_top
    overshoot_bot_target = font_desc - overshoot_bot  # bot=-20 -> desc+20 = shrink upward
    log.info(
        f"fix_block_elements: overshoot top={overshoot_top} bot={overshoot_bot} "
        f"-> block cell [{overshoot_bot_target}, {overshoot_top_target}]"
    )

    fixed = 0
    seen: set[str] = set()

    # Blocks (2580-259F), box drawing (2500-257F), and geometric triangles
    # (25E2-25E5) all come from the LXGW base and share its design box, so all
    # of them get the same design-cell -> font-cell rescale.  One shared linear
    # transform keeps stroke midlines and block boundaries aligned at the cell
    # center across the whole set.
    rescale_cps = set(
        list(range(0x2500, 0x25A0)) +
        list(range(0x25E2, 0x25E6))
    )

    # Powerline separators snap to exact cell edges (no overshoot).
    # These glyphs have curves/diagonals whose visual center shifts if overshoot
    # is asymmetric.  macOS Terminal.app overshoot only helps rectangular fills;
    # on VTE / GNOME Terminal the asymmetry causes a visible ~1 px vertical shift.
    # fit_nerd_icons already stretches these to the exact line box; this pass is
    # a safety net for any near-edge stragglers.
    snap_exact_cps = set(POWERLINE_FILL_CPS)

    target_cps = list(rescale_cps) + list(snap_exact_cps)
    for cp in target_cps:
        if cp not in cmap:
            continue
        gname = cmap[cp]
        if gname in seen:
            continue
        seen.add(gname)
        g = glyf_table[gname]
        if g.numberOfContours <= 0:
            continue

        do_rescale = needs_rescale and cp in rescale_cps
        use_overshoot = cp in rescale_cps

        for i, (x, y) in enumerate(g.coordinates):
            # Phase 1: rescale from design cell to font cell (block elements only)
            if do_rescale:
                y = round(font_desc + (y - design_desc) / design_cell * font_cell)

            # Phase 2: snap near-edge coordinates
            # Use tolerance to catch verticals that fall slightly short of
            # the cell edge after rescaling (e.g. yMax=973 vs asc=977)
            if y >= font_asc - 10:
                y = overshoot_top_target if use_overshoot else font_asc
            elif y <= font_desc + 10:
                y = overshoot_bot_target if use_overshoot else font_desc

            g.coordinates[i] = (x, y)

        g.recalcBounds(glyf_table)
        fixed += 1

    log.info(f"fix_block_elements: fixed {fixed} glyphs")
