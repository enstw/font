import pytest
from fontTools.ttLib import TTFont
from font_lib.utils import fix_glyph_order, parse_debug_codepoints

def test_fix_glyph_order():
    font = TTFont()
    font.setGlyphOrder([".notdef", "space"])
    from fontTools.ttLib.tables._g_l_y_f import table__g_l_y_f, Glyph
    font["glyf"] = table__g_l_y_f()
    font["glyf"].glyphs = {}
    font["glyf"].glyphOrder = font.getGlyphOrder()
    font["glyf"]["space"] = Glyph()
    font["glyf"][".notdef"] = Glyph()
    font["glyf"]["A"] = Glyph()
    font["glyf"]["B"] = Glyph()

    # When we add glyphs to glyf table, they might be added to its internal glyphOrder
    # but the top-level font.glyphOrder remains unchanged until setGlyphOrder is called.
    
    # Simulate a situation where glyf table has more glyphs than the font's main glyphOrder
    # In real fontTools usage, this often happens during transplantation
    font.glyphOrder = [".notdef", "space"]
    
    # Ensure our check passes before fix_glyph_order
    assert font.getGlyphOrder() == [".notdef", "space"]
    
    fix_glyph_order(font)
    
    # Should now have A and B in order, sorted
    assert font.getGlyphOrder() == [".notdef", "space", "A", "B"]

def test_parse_debug_codepoints():
    assert parse_debug_codepoints(["A"]) == [ord("A")]
    assert parse_debug_codepoints(["U+0041"]) == [0x41]
    assert parse_debug_codepoints(["0x41"]) == [0x41]
    
    with pytest.raises(ValueError):
        parse_debug_codepoints(["long_string"])
