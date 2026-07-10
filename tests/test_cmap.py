import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from font_lib.cmap import (
    get_best_cmap,
    ensure_cmap_subtables,
    glyph_name_for_codepoint,
    dealias_cmap,
)
from font_lib.utils import fix_glyph_order

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


def build_aliased_font():
    """Real minimal TTF: several codepoints share glyphs, as in WenKai."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    fb = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef", "uni9304", "square", "uni0041"]
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({
        0x9304: "uni9304",  # 錄 — canonical (matches glyph name)
        0x9332: "uni9304",  # 録 — variant alias
        0x20000: "uni9304", # non-BMP alias (format 12 path)
        0x25A0: "square",   # no uniXXXX name -> keep lowest
        0x25A1: "square",
        0x0041: "uni0041",  # already unique, must be untouched
    })
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((0, 700)); pen.lineTo((500, 700)); pen.lineTo((500, 0)); pen.closePath()
    box = pen.glyph()
    fb.setupGlyf({g: box for g in glyph_order})
    fb.setupHorizontalMetrics({g: (600, 0) for g in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Mock", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


def test_dealias_cmap():
    font = build_aliased_font()
    remapped = dealias_cmap(font)
    assert remapped == 3  # 0x9332, 0x20000, 0x25A1

    cmap = get_best_cmap(font)
    # kept codepoints still on the original glyphs
    assert cmap[0x9304] == "uni9304"   # name match wins
    assert cmap[0x25A0] == "square"    # lowest wins without a uniXXXX name
    assert cmap[0x0041] == "uni0041"   # unique mapping untouched
    # alias codepoints remapped to duplicate glyphs
    assert cmap[0x9332] == "ali_uni9332"
    assert cmap[0x20000] == "ali_u020000"
    assert cmap[0x25A1] == "ali_uni25A1"

    # reverse mapping is now unique
    seen = {}
    for cp, g in cmap.items():
        assert g not in seen, f"glyph {g} still shared by {seen[g]:#x} and {cp:#x}"
        seen[g] = cp

    # duplicates are composites referencing the original, with copied metrics
    dup = font["glyf"]["ali_uni9332"]
    assert dup.isComposite()
    assert dup.components[0].glyphName == "uni9304"
    assert font["hmtx"]["ali_uni9332"] == font["hmtx"]["uni9304"]

    # non-BMP alias must not leak into BMP (format 4) subtables
    for sub in font["cmap"].tables:
        if sub.format == 4:
            assert 0x20000 not in sub.cmap

    # fix_glyph_order reconciles the new glyphs (pipeline contract)
    fix_glyph_order(font)
    order = font.getGlyphOrder()
    assert "ali_uni9332" in order and "ali_u020000" in order

    # idempotent
    assert dealias_cmap(font) == 0
