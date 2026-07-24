# ENS Font — Elegant Nerd Sino

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/enstw/font/build-release.yml?branch=main&label=Build" alt="Build Status">
  <img src="https://img.shields.io/github/v/release/enstw/font?label=Version" alt="Latest Version">
  <img src="https://img.shields.io/github/license/enstw/font?label=License" alt="License">
</p>

> 讓你的終端機不僅能寫 Code，還能優雅地讀詩。
> 
> Let your terminal not only write code, but also read poetry elegantly.

🌐 **Official Home / 官方首頁**: [ens.tw/font](https://ens.tw/font)

---

**ENS Font** is a hybrid font designed for developers who value CJK (Chinese, Japanese, Korean) aesthetics. All text — CJK **and** ASCII/Latin — comes from **LXGW WenKai TC** (霞鶩文楷) with its poetic brush strokes, augmented with the full **Nerd Fonts** icon set (PUA) for terminal use.

**ENS Font** 是一款專為注重中英文字型美感的開發者設計的混合字型。所有文字（CJK **與** ASCII/拉丁）皆來自 **霞鶩文楷 (LXGW WenKai TC)** 優雅的書寫感，並補上完整的 **Nerd Fonts** 圖標集（PUA），適合終端機使用。

## 📥 Quick Start / 快速開始

Download the latest version from the [GitHub Releases](https://github.com/enstw/font/releases/latest).

| File / 檔案 | Description / 說明 |
| :--- | :--- |
| `ENSFont-X.Y.Z.zip` | Complete package (All TTFs + TTC) / 完整包 |
| **`ENSFont.ttc`** | **Recommended.** All-in-one bundle for all variants / **建議下載**，包含所有變體的集合檔 |
| `ENSFont-*.ttf` | Individual Proportional fonts / 全比例混合字體 |
| `ENSFontMono-*.ttf` | Strict Monospace (1-cell icons) / 嚴格等寬字體（1-cell 圖標） |
| `ENSFontMonoProp-*.ttf` | Mixed Monospace (Large icons) / 混合等寬（大圖標，相容 Ubuntu Terminal） |

## ✨ Variants / 產物說明

| Variant / 產物 | Text Base (incl. ASCII) | Icon Donor (PUA) | Characteristics / 特性 |
| :--- | :--- | :--- | :--- |
| **ENS Font** | WenKai TC | Symbols Nerd Font | Proportional spacing / 全比例混合 |
| **ENS Font Mono** | WenKai Mono TC | Symbols Nerd Font Mono | **Strictly Monospace** (500/1000 grid, 1-cell icons). Ideal for most terminals / 嚴格等寬，終端機首選 |
| **ENS Font Mono Prop** | WenKai Mono TC | Symbols Nerd Font | Mixed width. Large icons / 混合等寬，大圖標 |

*Available in **Regular** and **Bold**. We recommend using "Faux Italic" in your editor if needed.*
*提供 **Regular** 與 **Bold** 兩種字重。若需斜體，請在編輯器或終端機開啟 Faux Italic。*

## 🛠️ Implementation Logic / 合併邏輯

Rules: **If the donor font has the character, use it. Otherwise, fill from WenKai.**
規則：**Donor 有的字以 Donor 為準，其餘由 WenKai 補足。**

| Source / 來源 | Responsibility / 負責範圍 |
| :--- | :--- |
| **Symbols Nerd Font** | Nerd Font Icons (PUA), Powerline separators |
| **LXGW WenKai TC** | Everything else: ASCII, Latin, CJK (Hanzi/Kanji), Kana, Punctuation, Box drawing |

## ⚙️ Usage / 使用建議

### Visual Studio Code
```json
"editor.fontFamily": "'ENS Font Mono', monospace",
"editor.fontSize": 14,
"editor.lineHeight": 1.5
```

### Alacritty / iTerm2 / Terminal
Select **`ENS Font Mono`** to ensure perfect alignment of icons and text.
請選擇 **`ENS Font Mono`** 以確保圖標與文字完美對齊。

## 🏗️ Local Build / 本地建置

If you want to build the fonts yourself:

```bash
git clone https://github.com/enstw/font.git
cd font

# Setup environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt

# Download upstreams and run merge (example for Regular)
# See scripts/merge.py for all flags
python scripts/merge.py \
  --wenkai  path/to/LXGWWenKaiTC-Regular.ttf \
  --donor   path/to/SymbolsNerdFont-Regular.ttf \
  --output  dist/ENSFont-Regular.ttf \
  --style   Regular \
  --version 4.0.0 \
  --lxgw-version 1.522 \
  --nerd-version 3.4.0
```

## 🛠️ Diagnostic & Testing Tools / 診斷與測試工具

We provide utility scripts in the `utils/` directory for font developers to inspect metrics and test rendering:

- **`analyze_font_metrics.py`**: Inspects vertical metrics (OS/2, hhea) and reports block element/box-drawing coverage and overshoots.
- **`gen_cell_test_fonts.py`**: Generates variants of a font with different cell heights (e.g., 1.05em, 1.07em) to test line-gap behavior in various terminal emulators.

```bash
# Analyze a font
python3 utils/analyze_font_metrics.py dist/ENSFontMono-Regular.ttf

# Generate height variants for testing
python3 utils/gen_cell_test_fonts.py dist/ENSFontMono-Regular.ttf --em 1.07 1.10
```

## 🤝 Contributors / 貢獻者

- [@enstw](https://github.com/enstw) — Project Maintainer
- [Claude](https://github.com/claude) — AI Development Assistant
- [Gemini](https://gemini.google.com) — AI Development Assistant

## 📜 License / 授權

ENS Font is released under the **SIL Open Font License 1.1**.

| Component / 組件 | License / 授權 | Source / 來源 |
| :--- | :--- | :--- |
| [LXGW WenKai TC](https://github.com/lxgw/LxgwWenKaiTC) | SIL OFL 1.1 | Text Base (ASCII / Latin / CJK) |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) | MIT | Icons (PUA) |

*Reserved Font Names: **"ENS Font"** and **"Elegant Nerd Sino"**.*
*The upstream names "LXGW", "霞鶩", and "Klee" are NOT used in this derivative font.*
