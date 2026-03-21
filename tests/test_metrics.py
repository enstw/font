import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import table__g_l_y_f, Glyph
from scripts.font_lib.metrics import rebuild_vmtx

def create_mock_font_vmtx():
    font = TTFont()
    font.setGlyphOrder([".notdef", "space", "A"])
    
    # glyf
    font["glyf"] = glyf = table__g_l_y_f()
    glyf.glyphs = {}
    glyf.glyphOrder = font.getGlyphOrder()
    
    # .notdef (empty)
    glyf[".notdef"] = Glyph()
    
    # space (empty)
    glyf["space"] = Glyph()
    
    # A (with bounds)
    a_glyph = Glyph()
    a_glyph.numberOfContours = 1
    # We don't need real coordinates if we set yMax manually and it bypasses recalcBounds or recalcBounds works
    a_glyph.yMax = 700
    glyf["A"] = a_glyph
    
    # vhea
    from fontTools.ttLib.tables._v_h_e_a import table__v_h_e_a
    font["vhea"] = vhea = table__v_h_e_a()
    vhea.ascent = 1000
    vhea.advanceHeightMax = 1200
    vhea.numberOfVMetrics = 2 # Initial
    
    # vmtx
    from fontTools.ttLib.tables._v_m_t_x import table__v_m_t_x
    font["vmtx"] = vmtx = table__v_m_t_x()
    vmtx.metrics = {
        ".notdef": (1200, 0),
        "space": (1200, 0)
    }
    
    return font

def test_rebuild_vmtx():
    font = create_mock_font_vmtx()
    
    # Initially missing "A" in vmtx
    assert "A" not in font["vmtx"].metrics
    assert font["vhea"].numberOfVMetrics == 2
    
    rebuild_vmtx(font)
    
    # Should now have "A"
    assert "A" in font["vmtx"].metrics
    adv, tsb = font["vmtx"].metrics["A"]
    assert adv == 1200
    # tsb = vhea.ascent - yMax = 1000 - 700 = 300
    assert tsb == 300
    
    # numberOfVMetrics should be updated to total glyph count (3)
    assert font["vhea"].numberOfVMetrics == 3
