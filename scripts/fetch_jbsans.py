#!/usr/bin/env python3
"""
fetch_jbsans.py - Scrapes JetBrains homepage to locate, download, and convert
JetBrains Sans woff2 web fonts to TTF for use as ENS Font non-mono donor.

Strategy ("What You See Is What You Sign"):
  1. Fetch raw HTML from https://www.jetbrains.com/
  2. Extract CDN URLs for JetBrainsSans-*.woff2 via regex
  3. Detect version from the CDN URL path
  4. Download each woff2 and convert to TTF using fonttools
  5. Apply fallbacks for any styles not found on the page

Outputs (written to --output-dir):
  JetBrainsSans-Regular.ttf
  JetBrainsSans-Bold.ttf      (fallback: copy of Regular if not found)
  JetBrainsSans-Italic.ttf    (fallback: copy of Regular if not found)
  JetBrainsSans-BoldItalic.ttf (fallback: copy of Bold if not found)

Prints "VERSION=<ver>" as the last output line for CI consumption.

Usage:
    python scripts/fetch_jbsans.py --output-dir fonts/jetbrains_sans
"""

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

import requests
from fontTools.ttLib import TTFont

JETBRAINS_HOME = "https://www.jetbrains.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Regex: match CDN URLs for any JetBrainsSans-*.woff2 file
# Captures the style name (e.g. "Regular", "Bold") in group 1
WOFF2_PATTERN = re.compile(
    r"https://[a-zA-Z0-9\-\.]+/[a-zA-Z0-9\-\./]*/jetbrains-sans/[a-zA-Z0-9\-\./]*"
    r"/JetBrainsSans-([A-Za-z]+)\.woff2",
    re.IGNORECASE,
)

STYLES = ["Regular", "Bold", "Italic", "BoldItalic"]

# If a style is missing, copy from its fallback
FALLBACKS = {
    "Bold": "Regular",
    "Italic": "Regular",
    "BoldItalic": "Bold",
}


def fetch_homepage() -> str:
    print(f"Fetching {JETBRAINS_HOME} ...")
    resp = requests.get(JETBRAINS_HOME, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def find_woff2_urls(html: str) -> dict:
    """Return {style: url} dict from page HTML. First match per style wins."""
    found = {}
    for match in WOFF2_PATTERN.finditer(html):
        style = match.group(1)
        # Normalise common style name variants
        style = {"Bolditalic": "BoldItalic"}.get(style, style)
        if style not in found:
            found[style] = match.group(0)
            print(f"  Found {style}: {match.group(0)}")
    return found


def extract_version(urls: dict) -> str:
    """Extract version string from any CDN URL path segment."""
    for url in urls.values():
        # e.g. .../jetbrains-sans/2.304/JetBrainsSans-Regular.woff2
        #   or .../jetbrains-sans/v2.304/...
        m = re.search(r"/jetbrains-sans/v?(\d+[\.\d]+)/", url, re.IGNORECASE)
        if m:
            return m.group(1)
        # Generic version-like segment
        m = re.search(r"[/_]v?(\d+\.\d+(?:\.\d+)?)[/_]", url)
        if m:
            return m.group(1)
    return "unknown"


def download_woff2(url: str, dest: Path) -> None:
    print(f"  Downloading {Path(url).name} ...")
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def convert_woff2_to_ttf(woff2_path: Path, ttf_path: Path) -> None:
    font = TTFont(str(woff2_path))
    font.flavor = None  # strip WOFF2 wrapper → plain TTF/OTF
    font.save(str(ttf_path))
    print(f"  Converted → {ttf_path.name} ({ttf_path.stat().st_size // 1024} KB)")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch JetBrains Sans woff2 from JetBrains CDN and convert to TTF"
    )
    parser.add_argument(
        "--output-dir", default="fonts/jetbrains_sans",
        help="Output directory for TTF files (default: fonts/jetbrains_sans)"
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html = fetch_homepage()
    urls = find_woff2_urls(html)

    if not urls:
        print("ERROR: No JetBrains Sans woff2 URLs found on homepage.", file=sys.stderr)
        sys.exit(1)

    version = extract_version(urls)
    print(f"Detected JetBrains Sans version: {version}")

    converted: dict[str, Path] = {}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for style in STYLES:
            url = urls.get(style)
            if not url:
                continue
            woff2_file = tmp_path / f"JetBrainsSans-{style}.woff2"
            ttf_file = out_dir / f"JetBrainsSans-{style}.ttf"
            try:
                download_woff2(url, woff2_file)
                convert_woff2_to_ttf(woff2_file, ttf_file)
                converted[style] = ttf_file
            except Exception as e:
                print(f"  WARNING: Failed to fetch {style}: {e}", file=sys.stderr)

    if "Regular" not in converted:
        print("ERROR: Could not obtain JetBrainsSans-Regular.ttf (required).", file=sys.stderr)
        sys.exit(1)

    # Apply fallbacks for any missing styles
    for style, fallback in FALLBACKS.items():
        if style not in converted:
            src = converted.get(fallback)
            if src:
                dst = out_dir / f"JetBrainsSans-{style}.ttf"
                shutil.copy2(str(src), str(dst))
                converted[style] = dst
                print(f"  Fallback: {style} <- {fallback}")
            else:
                print(f"  WARNING: No fallback available for {style}", file=sys.stderr)

    print(f"\nOutput in {out_dir}/:")
    for style in STYLES:
        ttf = out_dir / f"JetBrainsSans-{style}.ttf"
        if ttf.exists():
            print(f"  {ttf.name} ({ttf.stat().st_size // 1024} KB)")

    # Last line: VERSION= for CI capture
    print(f"VERSION={version}")


if __name__ == "__main__":
    main()
