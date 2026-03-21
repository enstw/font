import logging
from fontTools.ttLib import TTFont

log = logging.getLogger(__name__)

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
