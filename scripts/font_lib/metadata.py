import logging
from datetime import datetime
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _n_a_m_e

log = logging.getLogger(__name__)

def set_font_metadata(
    font: TTFont,
    family_name: str,
    ps_family: str,
    style: str,
    version: str,
    lxgw_ver: str,
    nerd_ver: str,
) -> None:
    """
    Set all name table entries for OFL compliance and correct font identification.

    OFL 1.1 compliance requires:
    - Do NOT use reserved names: "LXGW", "霞鶩", "Klee"
    - Our reserved names: "ENS Font", "Elegant Nerd Sino"

    Name IDs set:
      0  Copyright
      1  Font Family name
      2  Font Subfamily name (Regular/Bold/Italic/Bold Italic)
      3  Unique font identifier
      4  Full font name
      5  Version string
      6  PostScript name (no spaces, A-Za-z0-9- only)
      8  Manufacturer
      11 URL Vendor
      13 License description
      14 License URL
      16 Preferred/Typographic Family name (modern apps use this for family grouping)
      19 Sample text
    """
    name_table = font["name"]

    ps_style = style.replace(" ", "")
    full_name = f"{family_name} {style}"
    ps_name = f"{ps_family}-{ps_style}"
    version_str = f"Version {version}; lxgw{lxgw_ver}; nerd{nerd_ver}"
    unique_id = f"{version_str}; {ps_name}"

    copyright_notice = (
        "ENS Font (Elegant Nerd Sino) is a derivative work.\n"
        "CJK glyphs: LXGW WenKai / WenKai Mono (c) 2021 Xiaocheng Liao, SIL OFL 1.1\n"
        "Latin/ASCII glyphs: Meslo LG (c) 2009, 2010, 2013 Andre Berg, Apache License 2.0\n"
        "Nerd patch and PUA icons: Nerd Fonts (c) 2014 Ryan L McIntyre, MIT License\n"
        f"Compiled font: (c) {datetime.now().year} enstw (https://ens.tw/font), SIL OFL 1.1\n"
        'Reserved Font Names: "ENS Font" and "Elegant Nerd Sino".\n'
        'The names "LXGW", "霞鶩", and "Klee" are NOT used by this derivative.'
    )

    license_text = (
        "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
        "This license is available with a FAQ at: https://openfontlicense.org. "
        "ASCII/Latin glyphs derived from Meslo LG are used under the Apache License 2.0."
    )

    entries = [
        (0, copyright_notice),
        (1, family_name),
        (2, style),
        (3, unique_id),
        (4, full_name),
        (5, version_str),
        (6, ps_name),
        (8, "enstw"),
        (9, "ENSFont"),
        (11, "https://ens.tw/font"),
        (13, license_text),
        (14, "https://openfontlicense.org"),
        (16, family_name),
        (
            19,
            "ENS:  main  ⇡1 ⇣0  ✚2 ~1 -0  |  git commit -m '修正字型預覽'  ✓ ；Elegant Nerd Sino：English + 繁體中文 + 简体中文 + 日本語 + 한국어。",
        ),
    ]

    # Clear ALL name records to ensure no leftover "LXGW" or "霞鶩" names from WenKai base
    name_table.names = []

    # Write Unicode-capable records first to avoid '?' replacement in preview text.
    # Keep zh-TW first for better TC classification and keep en-US as fallback.
    for name_id, value in entries:
        for platform_id, enc_id, lang_id in [
            (0, 4, 0),  # Unicode 2.0+ (full repertoire)
            (3, 1, 0x0404),  # zh-TW (Windows)
            (3, 1, 0x0409),  # en-US (Windows fallback)
        ]:
            record = _n_a_m_e.NameRecord()
            record.nameID = name_id
            record.platformID = platform_id
            record.platEncID = enc_id
            record.langID = lang_id
            if platform_id in (0, 3):
                record.string = value.encode("utf-16-be")
            name_table.names.append(record)

    log.info(f"Font name set: {full_name} / PS: {ps_name}")


def set_monospaced_metadata(font: TTFont, is_mono: bool) -> None:
    """
    Set metadata flags that tell terminal emulators this is a monospaced font.
    - post.isFixedPitch: 1 for mono, 0 for proportional
    - OS/2.panose.bProportion: 9 for mono, 0 (any) or 2 (proportional)
    - OS/2.panose.bSerifStyle: 0 (Any) — inherited from WenKai base as 2 (Cove),
      which incorrectly classifies this sans-serif font as serifed. Reset to 0 to
      match the donor family and avoid wrong font-substitution matches.
    - OS/2.xAvgCharWidth: Set to width of 'h' (approximate)
    - OS/2.achVendID: Set to 'ENSF' (ENS Font)
    """
    post = font["post"]
    os2 = font["OS/2"]

    # Set Vendor ID (4-character tag)
    os2.achVendID = "ENSF"

    # bSerifStyle=2 (Cove) is inherited from WenKai and is wrong for a sans-serif font.
    # Set to 0 (Any) to avoid incorrect serif font substitution.
    os2.panose.bSerifStyle = 0

    if is_mono:
        log.info("Setting monospaced flags (isFixedPitch=1, Panose=9)")
        post.isFixedPitch = 1
        os2.panose.bProportion = 9
    else:
        log.info("Setting proportional flags (isFixedPitch=0, Panose=2)")
        post.isFixedPitch = 0
        if os2.panose.bProportion == 9:
            os2.panose.bProportion = 2
