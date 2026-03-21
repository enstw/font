#!/usr/bin/env python3
"""
bundle_ttc.py - Bundle individual ENS Font TTFs into a TrueType Collection (.ttc).

Combines all TTF files in the dist/ directory into a single .ttc file with
shared tables (glyf, loca, etc.) to reduce total distribution size.

Usage:
    python scripts/bundle_ttc.py --input-dir dist/ --output dist/ENSFont.ttc
"""

import argparse
import logging
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.ttCollection import TTCollection

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Canonical order: non-mono first, then mono, then mono-prop
FONT_ORDER = [
    "ENSFont-Regular.ttf",
    "ENSFont-Bold.ttf",
    "ENSFontMono-Regular.ttf",
    "ENSFontMono-Bold.ttf",
    "ENSFontMonoProp-Regular.ttf",
    "ENSFontMonoProp-Bold.ttf",
]


def bundle_ttc(input_dir: str, output_path: str) -> None:
    input_dir = Path(input_dir)
    output = Path(output_path)

    # Collect TTF files in canonical order
    fonts: list[TTFont] = []
    for filename in FONT_ORDER:
        ttf_path = input_dir / filename
        if not ttf_path.exists():
            log.error(f"Missing expected TTF: {ttf_path}")
            raise FileNotFoundError(ttf_path)
        log.info(f"Loading {filename} ...")
        fonts.append(TTFont(ttf_path))

    log.info(f"Bundling {len(fonts)} fonts into TTC ...")
    collection = TTCollection()
    collection.fonts = fonts

    output.parent.mkdir(parents=True, exist_ok=True)
    collection.save(str(output))

    # Report sizes
    ttf_total = sum((input_dir / f).stat().st_size for f in FONT_ORDER)
    ttc_size = output.stat().st_size
    savings = (1 - ttc_size / ttf_total) * 100 if ttf_total else 0

    log.info(f"Individual TTFs total: {ttf_total // 1024:,} KB")
    log.info(f"TTC file size:         {ttc_size // 1024:,} KB")
    log.info(f"Savings:               {savings:.1f}%")
    log.info(f"Output: {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Bundle ENS Font TTFs into a TrueType Collection (.ttc)"
    )
    parser.add_argument(
        "--input-dir",
        default="dist",
        help="Directory containing the ENS Font TTF files (default: dist)",
    )
    parser.add_argument(
        "--output",
        default="dist/ENSFont.ttc",
        help="Output .ttc path (default: dist/ENSFont.ttc)",
    )
    args = parser.parse_args()

    bundle_ttc(args.input_dir, args.output)


if __name__ == "__main__":
    main()
