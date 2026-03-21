import logging
from fontTools.ttLib import TTFont

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
