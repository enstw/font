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


def dealias_cmap(font: TTFont, prefix: str = "ali_") -> int:
    """
    Give every Unicode codepoint its own glyph (one glyph per codepoint).

    LXGW WenKai maps variant/compatibility codepoints onto shared glyphs
    (錄/録, 內/内, 為/爲, U+3000/U+2003 and Unicode compatibility ideographs).
    Rendering is correct, but a PDF's ToUnicode CMap can map each glyph back
    to only ONE codepoint, so text copied or searched in a generated PDF may
    come back as the variant codepoint instead of the typed one.

    For every glyph reachable from more than one codepoint, keep exactly one
    codepoint on the original glyph (the one matching its uniXXXX-style
    production name when possible, else the lowest) and remap each remaining
    codepoint to a new composite glyph referencing the original — identical
    outlines and metrics. Codepoint coverage is unchanged; the
    glyph -> codepoint reverse mapping becomes unique.

    Adds glyphs to glyf/hmtx (and vmtx when present) only — run
    fix_glyph_order afterwards to reconcile the glyph order (merge.py does).

    Returns the number of alias codepoints remapped. Idempotent: a second
    run finds no multi-mapped glyphs and returns 0.
    """
    import re
    from collections import defaultdict
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

    ROUND_XY_TO_GRID = 0x0004
    USE_MY_METRICS = 0x0200

    best = get_best_cmap(font)
    glyph_to_codes = defaultdict(set)
    for code, gname in best.items():
        glyph_to_codes[gname].add(code)
    multi = {g: sorted(cs) for g, cs in glyph_to_codes.items() if len(cs) > 1}
    if not multi:
        return 0

    glyf = font["glyf"]
    hmtx = font["hmtx"]
    vmtx = font["vmtx"] if "vmtx" in font else None
    existing = set(font.getGlyphOrder()) | set(glyf.keys())
    uni_re = re.compile(r"^(?:uni([0-9A-F]{4})|u([0-9A-F]{4,6}))$")

    remapped = 0
    for gname, codes in sorted(multi.items(), key=lambda kv: kv[1][0]):
        m = uni_re.match(gname)
        named_cp = int(m.group(1) or m.group(2), 16) if m else None
        keep = named_cp if named_cp in codes else codes[0]
        for cp in codes:
            if cp == keep:
                continue
            new_name = glyph_name_for_codepoint(cp, prefix)
            while new_name in existing:
                new_name += ".alt"
            comp = GlyphComponent()
            comp.glyphName = gname
            comp.x, comp.y = 0, 0
            comp.flags = ROUND_XY_TO_GRID | USE_MY_METRICS
            dup = Glyph()
            dup.numberOfContours = -1
            dup.components = [comp]
            glyf[new_name] = dup
            hmtx[new_name] = hmtx[gname]
            if vmtx is not None and gname in vmtx.metrics:
                vmtx[new_name] = vmtx[gname]
            existing.add(new_name)
            update_cmap(font, cp, new_name)
            remapped += 1

    log.info(f"De-aliased {remapped} codepoints across {len(multi)} shared glyphs")
    return remapped
