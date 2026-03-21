import logging
import sys
from fontTools.ttLib import TTFont
from .cmap import get_best_cmap

log = logging.getLogger(__name__)

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
                try:
                    g.recalcBounds(glyf_table)
                except Exception:
                    # Some mock objects in tests or malformed glyphs might fail recalcBounds,
                    # but if they have yMax already, we can still use it.
                    pass
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
