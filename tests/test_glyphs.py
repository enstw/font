import pytest
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.font_lib.glyphs import fit_nerd_icons, ICON_INK_GAP

CELL = 500
UPM = 1000


def _rect_glyph(x0, y0, x1, y1):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def _mock_font(icons):
    """
    Build a minimal merged-font stand-in.
    icons: {codepoint: (glyph, advance)} — glyphs get the donor 'don_' prefix.
    """
    font = TTFont()
    names = [".notdef"] + [f"don_u{cp:04X}" for cp in icons]
    font.setGlyphOrder(names)

    font["glyf"] = glyf = newTable("glyf")
    glyf.glyphs = {}
    glyf.glyphOrder = names
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    glyf[".notdef"] = Glyph()

    font["hmtx"] = hmtx = newTable("hmtx")
    hmtx.metrics = {".notdef": (CELL, 0)}

    sub = CmapSubtable.getSubtableClass(12)()
    sub.platformID, sub.platEncID, sub.language = 3, 10, 0
    sub.format = 12
    sub.cmap = {}
    font["cmap"] = cmap = newTable("cmap")
    cmap.tableVersion = 0
    cmap.tables = [sub]

    for cp, (glyph, adv) in icons.items():
        name = f"don_u{cp:04X}"
        glyf[name] = glyph
        glyph.recalcBounds(glyf)
        hmtx.metrics[name] = (adv, glyph.xMin)
        sub.cmap[cp] = name

    font["head"] = head = newTable("head")
    head.unitsPerEm = UPM
    font["hhea"] = hhea = newTable("hhea")
    hhea.ascent, hhea.descent = 928, -241
    return font


def _mock_donor():
    donor = TTFont()
    donor["hhea"] = hhea = newTable("hhea")
    hhea.ascent, hhea.descent = 800, -200
    return donor


def test_mono_prop_clamps_oversized_icon_ink():
    # U+F327-like: ink 1335 units wide, far beyond the 2-cell budget
    font = _mock_font({0xF327: (_rect_glyph(0, 0, 1335, 700), 1335)})
    fit_nerd_icons(font, _mock_donor(), cell_width=CELL, fit_all=False)

    g = font["glyf"]["don_uF327"]
    adv, lsb = font["hmtx"].metrics["don_uF327"]
    budget = 2 * CELL
    assert adv == budget
    assert lsb == g.xMin
    # ink fits the budget with the gap honored on both sides
    assert g.xMin >= ICON_INK_GAP - 1
    assert g.xMax <= budget - ICON_INK_GAP + 1
    # uniform scale: aspect ratio preserved (within rounding)
    ink_w, ink_h = g.xMax - g.xMin, g.yMax - g.yMin
    assert ink_h == pytest.approx(ink_w * 700 / 1335, abs=2)


def test_mono_prop_keeps_icons_within_budget_untouched():
    # U+E712-like: ink 645 wide — fits icon cell + trailing space, stays native
    font = _mock_font({0xE712: (_rect_glyph(0, 0, 645, 600), 645)})
    fit_nerd_icons(font, _mock_donor(), cell_width=CELL, fit_all=False)

    g = font["glyf"]["don_uE712"]
    adv, _ = font["hmtx"].metrics["don_uE712"]
    assert adv == 645  # advance untouched; normalize_half_widths snaps it later
    assert (g.xMin, g.xMax, g.yMin, g.yMax) == (0, 645, 0, 600)


def test_proportional_build_never_clamps():
    font = _mock_font({0xF327: (_rect_glyph(0, 0, 1335, 700), 1335)})
    fit_nerd_icons(font, _mock_donor(), cell_width=None, fit_all=False)

    g = font["glyf"]["don_uF327"]
    adv, _ = font["hmtx"].metrics["don_uF327"]
    assert adv == 1335
    assert (g.xMin, g.xMax) == (0, 1335)
