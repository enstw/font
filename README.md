# ENS Font — Elegant Nerd Sino

> 讓你的終端機不僅能寫 Code，還能優雅地讀詩。

🌐 **官方首頁與載點**：[ens.tw](https://ens.tw/font)

開發者長期在「完美的英文等寬字體」與「優雅不擠壓的中文顯示」之間妥協。ENS Font 不是縫合怪——它是一條生產線：兩款字體各司其職，上游一有更新，CI 自動重新建置並發布。

**E · N · S** 三個字母定義了這套字體的架構：

- **E (Elegant)**：霞鶩文楷的文青氣質，讓中文在終端機裡也能好看
- **N (Nerd)**：Nerd Fonts 數萬種 PUA 圖標，Powerline 主題完整支援
- **S (Sino)**：廣闊的 CJK 字元庫作為基底，穩穩接住所有中日韓文字

---

## 合併邏輯

以 **LXGW WenKai / LXGW WenKai Mono** 為基底，將 Nerd Fonts donor 字型移植進去：

| 來源 | 負責範圍 |
|------|---------|
| **MesloLGMNerdFont / JetBrainsMonoNerdFontMono**（優先） | donor 字型涵蓋的所有字元，一律優先覆蓋 WenKai |
| **LXGW WenKai**（補充） | 僅保留 donor 沒有的字元，主要為 CJK、假名、全形標點等 |

規則只有一條：**donor 有的字以 donor 為準，其餘由 WenKai 補足。**

目前產物對應如下：

| 產物 | CJK 基底 | Donor 來源 |
|------|---------|------------------|
| ENS Font | LXGW WenKai | MesloLGMNerdFont |
| ENS Font Mono | LXGW WenKai Mono | JetBrainsMonoNerdFontMono |

---

## 字重說明

LXGW WenKai / LXGW WenKai Mono 皆提供 Regular / Medium / Light 三種字重（無 Bold）。ENS Font 與 ENS Font Mono 對應如下：

| 產物 | 字重 | WenKai CJK 來源 | Donor 來源 |
|------|------|----------------|------------------|
| ENS Font | Regular | Regular | MesloLGMNerdFont-Regular |
| ENS Font | Bold | Medium（最接近） | MesloLGMNerdFont-Bold |
| ENS Font | Italic | Regular | MesloLGMNerdFont-Italic |
| ENS Font | Bold Italic | Medium | MesloLGMNerdFont-BoldItalic |
| ENS Font Mono | Regular | Regular | JetBrainsMonoNerdFontMono-Regular |
| ENS Font Mono | Bold | Medium（最接近） | JetBrainsMonoNerdFontMono-Bold |
| ENS Font Mono | Italic | Regular | JetBrainsMonoNerdFontMono-Italic |
| ENS Font Mono | Bold Italic | Medium | JetBrainsMonoNerdFontMono-BoldItalic |

---

## 快速安裝

### 方法一：直接下載（推薦）

1. 前往 [Releases 頁面](../../releases)
2. 下載最新版本的 `ENSFont-{version}.zip`
3. 解壓縮，全選字體檔案安裝至系統
4. 在終端機或編輯器中將字體設為 `ENS Font`（或 `ENS Font Mono`）

**iTerm2**：Preferences → Profiles → Text → Font → 選擇 `ENS Font`

**VS Code**：`"editor.fontFamily": "ENS Font"`

**Windows Terminal**：`"fontFace": "ENS Font"`

### 方法二：Homebrew（macOS，即將支援）

```bash
# Coming soon
# brew tap enstw/fonts
# brew install --cask font-ens
```

---

## 自動更新機制

本專案透過 GitHub Actions 全自動維護，無需人工介入：

```
每日 06:00 UTC
    └── check-upstream.yml
            ├── 查詢 lxgw/LxgwWenKai 最新 release
            ├── 查詢 ryanoasis/nerd-fonts 最新 release
            └── 若有更新 → 觸發 build-release.yml
                    ├── 下載最新上游字體
                    ├── 執行合併腳本（8 個產物並行）
                    ├── OFL 合規自動驗證
                    └── 發布新版 GitHub Release
```

---

## 本地建置

```bash
git clone https://github.com/enstw/font.git
cd font

python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt

# 下載上游字體
mkdir -p fonts/wenkai fonts/meslo fonts/jetbrainsmono
curl -fL "https://github.com/lxgw/LxgwWenKai/releases/latest/download/LXGWWenKai-Regular.ttf" \
     -o fonts/wenkai/LXGWWenKai-Regular.ttf
curl -fL "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Meslo.tar.xz" \
     -o /tmp/Meslo.tar.xz && tar -xJf /tmp/Meslo.tar.xz -C fonts/meslo/
curl -fL "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz" \
     -o /tmp/JetBrainsMono.tar.xz && tar -xJf /tmp/JetBrainsMono.tar.xz -C fonts/jetbrainsmono/

# 合併
python scripts/merge.py \
  --wenkai  fonts/wenkai/LXGWWenKai-Regular.ttf \
  --meslo   fonts/meslo/MesloLGMNerdFont-Regular.ttf \
  --output  dist/ENSFont-Regular.ttf \
  --style   Regular \
  --version 1.0.0 \
  --lxgw-version 1.521 \
  --nerd-version 3.4.0
```

---

## 授權

ENS Font 的最終輸出字體以 **SIL Open Font License 1.1** 發布。

| 來源 | 授權 | 用途 |
|------|------|------|
| [LXGW WenKai / LXGW WenKai Mono](https://github.com/lxgw/LxgwWenKai) | SIL OFL 1.1 | CJK 字元基底 |
| [MesloLGM](https://github.com/andreberg/Meslo-Font) | Apache 2.0 | ASCII / 拉丁字元 |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) | MIT | PUA 終端機圖標 |

保留字型名稱（Reserved Font Names）：**"ENS Font"** 與 **"Elegant Nerd Sino"**。

原始字體的保留名稱 "LXGW"、"霞鶩"、"Klee"、"Meslo" 均**未使用**於本衍生字體。
