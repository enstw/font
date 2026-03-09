# Idea of Automated JetBrains Sans (Non-Mono) Downloader & Converter

## 1. Context & Objective
The goal is to establish a stable, automated pipeline to track, download, and convert the **non-monospaced** version of JetBrains Sans for CLI and terminal usage. 

This font is proprietary and does not have a public GitHub release page. To ensure we always get the authentic, production-ready version (adhering to a "What You See Is What You Sign" philosophy), we will actively scrape the live JetBrains homepage to extract the font's CDN URL, rather than guessing version numbers.

**Key Requirements:**
* **Target Font:** JetBrains Sans (Non-Mono), specifically the `1IlO0` high-legibility glyphs used in their UI.
* **Format:** Must convert the downloaded Web Font (`.woff2`) into a standard Desktop Font (`.ttf`).
* **Deployment Environment:** This script will be deployed as a Cron job on a Raspberry Pi 5 running a ZFS NAS.

## 2. Strategy (The Source Monitor Approach)
Instead of relying on unstable third-party APIs or guessing version increments, the script must:
1.  Fetch the raw HTML of `https://www.jetbrains.com/`.
2.  Use Regex to locate the active CDN link for `JetBrainsSans-Regular.woff2`.
3.  Extract the version number from the URL for local state comparison.
4.  If a new version is detected, download the `.woff2` file.
5.  Use Python's `fonttools` to unpack the Brotli compression and save it as a valid `.ttf` file.

## 3. Implementation Details

### Dependencies
Please ensure the script uses the following Python packages:
* `requests` (for HTTP fetching)
* `fonttools` (for font table manipulation)
* `brotli` (required by fonttools to decompress woff2)

### Reference Python Script
Use the following logic to build the automation script:

```python
import requests
import re
import os
from fontTools.ttLib import TTFont

def track_and_download_jetbrains_sans():
    url = "[https://www.jetbrains.com/](https://www.jetbrains.com/)"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text
    except Exception as e:
        print(f"Failed to fetch webpage: {e}")
        return

    # Regex to find the WOFF2 CDN link
    pattern = r"https://[a-zA-Z0-9\-\.\/]+/jetbrains-sans/[a-zA-Z0-9\-\.\/]+/JetBrainsSans-Regular\.woff2"
    match = re.search(pattern, html_content)

    if match:
        font_url = match.group(0)
        version_match = re.search(r"v\d+\.\d+", font_url)
        version = version_match.group(0) if version_match else "unknown_version"
        
        # Target ZFS dataset path on Raspberry Pi 5
        local_dir = "/mnt/zfs_pool/fonts_archive/jetbrains_sans"
        os.makedirs(local_dir, exist_ok=True)
        
        ttf_filename = f"JetBrainsSans-Regular-{version}.ttf"
        ttf_filepath = os.path.join(local_dir, ttf_filename)
        
        if not os.path.exists(ttf_filepath):
            print(f"New version detected: {version}. Downloading...")
            
            woff2_path = os.path.join(local_dir, "temp.woff2")
            font_data = requests.get(font_url, headers=headers).content
            with open(woff2_path, "wb") as f:
                f.write(font_data)
            
            # Convert WOFF2 to TTF
            try:
                font = TTFont(woff2_path)
                font.flavor = None # Removes WOFF2 wrapper
                font.save(ttf_filepath)
                print(f"Success: Saved to {ttf_filepath}")
            except Exception as e:
                print(f"Font conversion failed: {e}")
            finally:
                if os.path.exists(woff2_path):
                    os.remove(woff2_path)
        else:
            print(f"Version {version} already exists. No action needed.")
    else:
        print("Warning: JetBrains Sans link not found on the homepage.")

if __name__ == "__main__":
    track_and_download_jetbrains_sans()