# 🌟 ENS Font (Elegant Nerd Sino Font)

> **讓你的終端機不僅能寫 Code，還能優雅地讀詩。**

🌐 **官方首頁與載點**：[ens.tw](https://ens.tw)

我們從 ENS Font 與市面上無數「字體縫合怪」**最顯著的不同**開始討論：**這不僅僅是一套字型，這是一個活的、全自動化更新的字型 CI/CD 工廠。**

寫程式或在終端機敲指令時，我們講求精準——打出來的字長什麼樣，系統就該完美呈現。但長久以來，開發者總在「完美的英文等寬字體」與「優雅不擠壓的中文顯示」之間妥協。**ENS Font** 應運而生，它的名字正是我們的方程式：

* **E (Elegant)**：保留霞鶩文楷自帶的文青屬性，提供排版舒適的優雅體驗。
* **N (Nerd)**：注入 Nerd Fonts 支援數萬種 PUA 圖形，解放終端機美化火力。
* **S (Sino)**：以廣闊的 CJK 字元庫作為基底，完美支撐龐大的中文生態。

這不只是一套字體，這是以 **基礎設施 (Infrastructure as Code)** 精神打造的開源藝術品。

---

## ✨ 核心特色

* **🔀 嚴格的字元覆寫邏輯 (Collision Resolution)**：在字體合併的過程中，本專案透過腳本嚴格執行以下優先權（Priority），確保每個字元都在它最擅長的位置：
  1. **👑 絕對優先 - MesloLGM**：強制覆寫所有 ASCII 與基本拉丁字元，守護程式碼的絕對等寬與完美對齊。
  2. **🛠️ 次要覆寫 - Nerd Fonts**：接管 Powerline 箭頭與終端機 UI 圖示，避免被中文字體干擾。
  3. **🌊 堅實基底 - LXGW WenKai**：作為最底層的汪洋大海，穩穩接住所有前兩者缺乏的 CJK（中日韓）字元。
* **🤖 零介入全自動更新**：利用 GitHub Actions 定期監控上游的 Release。一旦上游修復了錯字或新增了圖標，本專案會自動拉取、編譯、打包並發佈新版本。
* **⚖️ 完全開源合規**：嚴格遵守 SIL Open Font License 1.1 規範，乾淨俐落的重新命名與封裝，沒有版權疑慮。

---

## 🚀 快速安裝

### 方法一：直接下載 (推薦)
1. 前往本專案的 [Releases 頁面](../../releases) 或造訪 [ens.tw](https://ens.tw)。
2. 下載最新版本的 `ENS-Font.zip`。
3. 解壓縮後，全選字體檔案並安裝至系統。
4. 在你的終端機 (iTerm2, Windows Terminal) 或編輯器 (VS Code) 中，將字體設定為：`ENS Font` 或 `Elegant Nerd Sino`。

### 方法二：利用 Homebrew (macOS)
```bash
# 即將支援 Coming Soon...
# brew tap ens-font/fonts
# brew install --cask font-ens
