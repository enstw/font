# ENS Font — Elegant Nerd Sino

> 讓你的終端機不僅能寫 Code，還能優雅地讀詩。

🌐 **官方首頁與載點**：[ens.tw](https://ens.tw/font)

ENS Font 以 **LXGW WenKai TC / LXGW WenKai Mono TC** 為 CJK 基底，並改用 **Meslo LGSDZ Nerd Font** 作為英文、符號與終端圖標 donor。這次 donor 切換屬於 breaking change，因此從 `3.0.0` 開始計算新主版本。

## 合併邏輯

| 來源 | 負責範圍 |
|------|---------|
| **Meslo LGSDZ Nerd Font / Meslo LGSDZ Nerd Font Mono**（優先） | donor 字型涵蓋的所有字元，一律優先覆蓋 WenKai |
| **LXGW WenKai TC / WenKai Mono TC**（補充） | 僅保留 donor 沒有的字元，主要為 CJK、假名、全形標點等 |

規則只有一條：**donor 有的字以 donor 為準，其餘由 WenKai 補足。**

## 產物

| 產物 | CJK 基底 | Donor 來源 | 說明 |
|------|---------|------------|------|
| ENS Font | LXGW WenKai TC | Meslo LGSDZ Nerd Font | 全比例混合字體 |
| ENS Font Mono | LXGW WenKai Mono TC | Meslo LGSDZ Nerd Font Mono | 嚴格等寬字體（1-cell 圖標） |
| ENS Font Mono Prop | LXGW WenKai Mono TC | Meslo LGSDZ Nerd Font | 混合等寬（大圖標，相容 Ubuntu Terminal） |

## 字重與樣式說明

Meslo LGSDZ donor 目前在本專案只使用 **Regular / Bold** 兩個樣式，因此 ENS Font 也只發佈以下檔案：

| 檔案 | 字重 |
|------|------|
| `ENSFont-Regular.ttf` | Regular |
| `ENSFont-Bold.ttf` | Bold |
| `ENSFontMono-Regular.ttf` | Regular Mono |
| `ENSFontMono-Bold.ttf` | Bold Mono |
| `ENSFontMonoProp-Regular.ttf` | Regular Mono Prop |
| `ENSFontMonoProp-Bold.ttf` | Bold Mono Prop |

本專案不提供 Italic，也不再輸出 Light。若需要斜體效果，請在編輯器或終端機使用 faux italic。

## 自動更新機制

本專案透過 GitHub Actions 自動追蹤兩個上游：

```text
每日 06:00 UTC
    └── check-upstream.yml
            ├── 查詢 lxgw/LxgwWenKaiTC 最新 release
            ├── 查詢 ryanoasis/nerd-fonts 最新 release
            └── 若有更新 → 觸發 build-release.yml
                    ├── 下載 LXGW WenKai TC
                    ├── 下載 Meslo.tar.xz 並抽出 Meslo LGSDZ Nerd donors
                    ├── 執行合併腳本（4 個產物並行）
                    ├── OFL 合規自動驗證
                    └── 發布新版 GitHub Release
```

## 本地建置

```bash
git clone https://github.com/enstw/font.git
cd font

python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt

mkdir -p fonts/wenkai fonts/meslo dist

# 1. 下載 LXGW WenKai TC
curl -fL "https://github.com/lxgw/LxgwWenKaiTC/releases/latest/download/lxgw-wenkai-tc-v1.521.zip" \
  -o /tmp/lxgw-wenkai-tc.zip
unzip -j /tmp/lxgw-wenkai-tc.zip "*.ttf" -d fonts/wenkai/

# 2. 下載 Meslo LGSDZ Nerd Fonts
curl -fL "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Meslo.tar.xz" \
  -o /tmp/Meslo.tar.xz
tar -xJf /tmp/Meslo.tar.xz -C fonts/meslo/

# 3. 合併 (ENS Font)
python scripts/merge.py \
  --wenkai  fonts/wenkai/LXGWWenKaiTC-Regular.ttf \
  --donor   fonts/meslo/MesloLGSDZNerdFont-Regular.ttf \
  --output  dist/ENSFont-Regular.ttf \
  --style   Regular \
  --version 3.0.0 \
  --lxgw-version 1.521 \
  --nerd-version 3.4.0

# 4. 合併 (ENS Font Mono)
python scripts/merge.py \
  --wenkai  fonts/wenkai/LXGWWenKaiMonoTC-Regular.ttf \
  --donor   fonts/meslo/MesloLGSDZNerdFontMono-Regular.ttf \
  --output  dist/ENSFontMono-Regular.ttf \
  --style   Regular \
  --version 3.0.0 \
  --lxgw-version 1.521 \
  --nerd-version 3.4.0 \
  --mono
```

## 授權

ENS Font 的最終輸出字體以 **SIL Open Font License 1.1** 發布。

| 來源 | 授權 | 用途 |
|------|------|------|
| [LXGW WenKai TC / LXGW WenKai Mono TC](https://github.com/lxgw/LxgwWenKaiTC) | SIL OFL 1.1 | CJK 字元基底 |
| [Meslo LG](https://github.com/andreberg/Meslo-Font) | Apache 2.0 | ASCII / 拉丁字元來源 |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) | MIT | Nerd 補丁與 PUA 終端機圖標 |

保留字型名稱（Reserved Font Names）：**"ENS Font"** 與 **"Elegant Nerd Sino"**。

原始字體的保留名稱 "LXGW"、"霞鶩"、"Klee" 均**未使用**於本衍生字體。
