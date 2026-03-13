#!/usr/bin/env python3
"""
fetch_jbsans.py - Downloads JetBrains Sans variable TTF from JetBrains CDN
and instantiates static TTF files for each required weight/style.

Strategy:
  1. Fetch JetBrains homepage HTML and locate the default-page CSS URL
  2. Fetch that CSS and extract the variable font URL (contains version in path)
  3. Download JetBrainsSans[wght].ttf directly (no woff2 conversion needed)
  4. Instantiate static weights using fonttools.instancer:
       Light (wght=300), Regular (wght=400), Bold (wght=700)

Outputs (written to --output-dir):
  JetBrainsSans-Light.ttf
  JetBrainsSans-Regular.ttf
  JetBrainsSans-Bold.ttf

Prints "VERSION=<ver>" as the last output line for CI consumption.

Usage:
    python scripts/fetch_jbsans.py --output-dir fonts/jetbrains_sans
"""

import argparse
import re
import sys
from io import BytesIO
from pathlib import Path

import requests
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

JETBRAINS_HOME = "https://www.jetbrains.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Static instances to produce from the variable font
WEIGHT_INSTANCES = {
    "Light": 300,
    "Regular": 400,
    "Bold": 700,
}

STYLES = ["Light", "Regular", "Bold"]


def fetch_text(url: str, label: str) -> str:
    print(f"Fetching {label} ...")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def find_css_url(html: str) -> str | None:
    """Extract the default-page CSS path from homepage HTML."""
    m = re.search(r'"(/_assets/default-page\.[a-f0-9]+\.css)"', html)
    return m.group(1) if m else None


def find_variable_font_url(css: str) -> tuple[str, str]:
    """
    Extract variable font TTF URL and version from CSS.
    The CSS @font-face references a woff2 URL containing the version in the path;
    we swap .woff2 -> .ttf to download the plain TTF fallback directly.
    Returns (ttf_url, version_string).
    """
    m = re.search(
        r"(https://resources\.jetbrains\.com/storage/jetbrains-sans/google-fonts/"
        r"(v[\d.]+)/variable/JetBrainsSans\[wght\]\.woff2)",
        css,
    )
    if not m:
        return "", "unknown"
    version = m.group(2).lstrip("v")
    ttf_url = m.group(1).replace(".woff2", ".ttf")
    return ttf_url, version


def download_bytes(url: str, label: str) -> bytes:
    print(f"Downloading {label} ...")
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


def main():
    parser = argparse.ArgumentParser(
        description="Fetch JetBrains Sans variable TTF and instantiate static weights"
    )
    parser.add_argument(
        "--output-dir", default="fonts/jetbrains_sans",
        help="Output directory for TTF files (default: fonts/jetbrains_sans)"
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: locate the CSS file URL from homepage
    html = fetch_text(JETBRAINS_HOME, "JetBrains homepage")
    css_path = find_css_url(html)
    if not css_path:
        print("ERROR: Could not find default-page CSS URL in homepage.", file=sys.stderr)
        sys.exit(1)

    css_url = f"https://www.jetbrains.com{css_path}"
    css = fetch_text(css_url, f"CSS ({css_path.split('/')[-1]})")

    # Step 2: extract variable font TTF URL and version
    ttf_url, version = find_variable_font_url(css)
    if not ttf_url:
        print("ERROR: Could not find JetBrains Sans variable font URL in CSS.", file=sys.stderr)
        sys.exit(1)

    print(f"Detected JetBrains Sans version: {version}")
    print(f"Variable font URL: {ttf_url}")

    # Step 3: download variable TTF
    ttf_bytes = download_bytes(ttf_url, "JetBrainsSans[wght].ttf")
    var_font = TTFont(BytesIO(ttf_bytes))

    # Step 4: instantiate static weights
    print("Instantiating static weights...")
    produced: dict[str, Path] = {}
    for style, weight in WEIGHT_INSTANCES.items():
        print(f"  {style} (wght={weight})")
        static = instantiateVariableFont(var_font, {"wght": weight})
        out_path = out_dir / f"JetBrainsSans-{style}.ttf"
        static.save(str(out_path))
        print(f"    -> {out_path.name} ({out_path.stat().st_size // 1024} KB)")
        produced[style] = out_path

    print(f"\nOutput in {out_dir}/:")
    for style in STYLES:
        ttf = out_dir / f"JetBrainsSans-{style}.ttf"
        if ttf.exists():
            print(f"  {ttf.name} ({ttf.stat().st_size // 1024} KB)")

    # Last line: VERSION= for CI capture
    print(f"VERSION={version}")


if __name__ == "__main__":
    main()
