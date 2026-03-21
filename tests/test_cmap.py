import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from font_lib.cmap import get_best_cmap, ensure_cmap_subtables, glyph_name_for_codepoint

def create_mock_font(cmaps=None):
    font = TTFont()
    font["cmap"] = cmap_table = TTFont().get("cmap") or font.get("cmap")
    if not cmap_table:
        from fontTools.ttLib.tables._c_m_a_p import table__c_m_a_p
        font["cmap"] = cmap_table = table__c_m_a_p()
        cmap_table.tableVersion = 0
        cmap_table.tables = []
    
    if cmaps:
        for fmt, plat, enc, data in cmaps:
            sub = CmapSubtable.newSubtable(fmt)
            sub.platformID = plat
            sub.platEncID = enc
            sub.language = 0
            sub.cmap = data
            cmap_table.tables.append(sub)
    return font

def test_get_best_cmap_priorities():
    # Format 12 (Windows Unicode Full)
    data12 = {0x1F600: "grinning_face"}
    # Format 4 (Windows BMP)
    data4 = {0x0041: "A"}
    # Format 4 (Unicode platform)
    data0 = {0x0042: "B"}

    # Test format 12 priority
    font = create_mock_font([
        (12, 3, 10, data12),
        (4, 3, 1, data4)
    ])
    assert get_best_cmap(font) == data12

    # Test format 4 (Windows) priority over Unicode platform
    font = create_mock_font([
        (4, 3, 1, data4),
        (4, 0, 3, data0)
    ])
    assert get_best_cmap(font) == data4

    # Test Unicode platform fallback
    font = create_mock_font([
        (4, 0, 3, data0)
    ])
    assert get_best_cmap(font) == data0

def test_ensure_cmap_subtables():
    data = {0x0041: "A", 0x1F600: "grinning_face"}
    font = create_mock_font([(12, 3, 10, data)])
    
    # Initially only has format 12
    assert len(font["cmap"].tables) == 1
    assert font["cmap"].tables[0].format == 12

    ensure_cmap_subtables(font)
    
    # Should now have format 4 and 12
    formats = [t.format for t in font["cmap"].tables]
    assert 4 in formats
    assert 12 in formats
    
    # Format 4 should only have BMP codepoints
    f4 = next(t for t in font["cmap"].tables if t.format == 4)
    assert 0x0041 in f4.cmap
    assert 0x1F600 not in f4.cmap

def test_glyph_name_for_codepoint():
    assert glyph_name_for_codepoint(0x0041, "pre_") == "pre_uni0041"
    assert glyph_name_for_codepoint(0x1F600, "pre_") == "pre_u01F600"
