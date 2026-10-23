# 🗂️ Workspace Session Recorder

**一鍵記錄、一鍵復原 — 讓你的 Windows 工作區不再手動重開。**

Workspace Session Recorder 是一款專為 Windows 打造的桌面小工具，能夠即時掃描目前所有開啟的應用程式視窗與瀏覽器分頁網址，讓使用者勾選想保留的項目後，一鍵匯出成雙擊即可執行的 `.bat` 批次檔。下次只要執行該批次檔，就能瞬間復原整個工作區環境。

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/GUI-Tkinter-informational" alt="GUI Framework" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
</p>

### ✨ 核心優勢

| 標籤 | 說明 |
|------|------|
| 🚀 **非同步掃描不卡頓** | 視窗掃描與瀏覽器網址擷取皆於背景執行緒執行，介面全程保持順暢回應 |
| 🧭 **自動識別分頁網址** | 透過 Windows UI Automation 讀取 Chromium 系列瀏覽器目前分頁的真實網址 |
| 📦 **免安裝依賴** | 可打包為單一 `.exe` 執行檔，終端使用者無需安裝 Python 或任何套件 |
| 🛡️ **安全匯出批次檔** | 自動處理 UTF-8 BOM 編碼與 `%` 特殊字元跳脫，確保命令提示字元執行無誤 |

---

## 📋 目錄

- [主要功能](#-主要功能-features)
- [系統需求](#-系統需求-requirements)
- [快速開始](#-快速開始-getting-started)
- [打包為獨立執行檔](#-打包為獨立執行檔-exe)
- [專案目錄結構](#-專案目錄結構-project-structure)
- [測試執行](#-測試執行-testing)
- [開源授權](#-開源授權-license)

---

## 🔍 主要功能 (Features)

### 1. 應用程式掃描

- 透過 `win32gui` 的 `EnumWindows` API 自動掃描目前所有「可見」的頂層視窗。
- 自動過濾背景系統程序（如 `explorer.exe`、`cmd.exe`、`powershell.exe` 等），避免雜訊混入清單。
- 支援 **多虛擬桌面 / Cloaked 視窗過濾**：透過 DWM（`DwmGetWindowAttribute`）偵測並排除停留在其他虛擬桌面、實際未顯示在畫面上的「偽視窗」，避免誤判為開啟中的應用程式。
- 針對視窗於掃描過程中被關閉（如提示通知、暫時性視窗）等邊界情況進行例外處理，不會導致程式崩潰。

### 2. 瀏覽器 URL 擷取

- 透過 Windows **UI Automation**（`uiautomation` 套件）讀取網址列的 `Edit` 控制項內容。
- 支援主流 Chromium 系列瀏覽器：**Chrome、Edge、Brave、Opera（含 Opera GX）、Vivaldi、Chromium**。
- 非 Chromium 架構的瀏覽器（例如 Firefox）會自動且安全地「降級」為一般應用程式記錄（以執行檔路徑儲存），不會發生錯誤或崩潰。
- 內建搜尋深度與逾時上限，避免單一視窗卡住整體掃描速度。

### 3. 勾選過濾與直覺 UI

- 以表格化介面（Treeview）呈現掃描結果，點擊即可勾選／取消「是否要匯出」。
- 提供「全選」「取消全選」快速按鈕，方便批次調整。
- 掃描作業於**背景執行緒**進行，並透過佇列（Queue）安全地將結果傳回主執行緒更新畫面，期間介面不會凍結，使用者仍可自由操作視窗。
- 掃描中會自動停用「掃描」按鈕，避免重複觸發造成資料競爭。

### 4. 一鍵匯出 `.bat`

- 將勾選的項目轉換為一份可雙擊執行的 Windows 批次檔，內含多行 `start "" "目標路徑或網址"` 指令。
- 自動以 **UTF-8 with BOM** 格式寫入，確保檔案路徑或標題包含中文、日文等非英文字元時，`cmd.exe` 也能正確解析。
- 自動將路徑或網址中的 `%` 字元轉義為 `%%`，避免被 `cmd.exe` 誤判為環境變數（例如 `%TEMP%`）而導致路徑損毀。
- 自動跳過空白或無效的目標項目，並記錄警告訊息，不會產生壞掉的指令。

---

## 💻 系統需求 (Requirements)

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / Windows 11 |
| Python 版本 | 3.10 以上（**僅開發者需要**；一般使用者可直接使用打包好的 `.exe`） |
| 必要套件 | `pywin32`、`uiautomation`、`psutil`、`comtypes`（詳見 [requirements.txt](./requirements.txt)） |

> 💡 若你只是想使用這個工具，不需要安裝 Python，直接下載 / 自行打包出的 `WorkspaceRecorder.exe` 即可開箱使用。

---

## 🚀 快速開始 (Getting Started)

### 1️⃣ 複製專案

```powershell
git clone https://github.com/ChungChiuHung/workspace-session-recorder.git
cd workspace-session-recorder
```

### 2️⃣ 建立虛擬環境

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3️⃣ 安裝依賴套件

```powershell
pip install -r requirements.txt
```

> 若需要執行單元測試或參與開發，請改安裝開發用依賴：
>
> ```powershell
> pip install -r requirements-dev.txt
> ```

### 4️⃣ 啟動應用程式

```powershell
python src/app.py
```

啟動後即可點擊「🔍 掃描目前視窗」按鈕，勾選想保留的項目，再點擊「💾 匯出為 .bat 檔案」完成匯出。

---

## 📦 打包為獨立執行檔 (.exe)

若想將專案打包成**免安裝依賴、無主控台視窗**的單一執行檔，方便分享給其他 Windows 使用者，可使用 [PyInstaller](https://pyinstaller.org/)：

```powershell
pip install pyinstaller

pyinstaller --noconsole --onefile --name WorkspaceRecorder src/app.py
```

指令參數說明：

| 參數 | 說明 |
|------|------|
| `--noconsole` | 執行時不顯示黑色主控台（CMD）視窗，僅顯示 GUI 介面 |
| `--onefile` | 將所有相依檔案打包成單一 `.exe`，方便攜帶與分享 |
| `--name WorkspaceRecorder` | 指定輸出的執行檔名稱為 `WorkspaceRecorder.exe` |

打包完成後，可於專案根目錄下的 `dist/` 資料夾中找到 `WorkspaceRecorder.exe`，雙擊即可直接執行，無需安裝 Python 或任何相依套件。

> 📝 專案已內附 [`WorkspaceRecorder.spec`](./WorkspaceRecorder.spec) 設定檔，日後若需重新打包，也可直接執行：
>
> ```powershell
> pyinstaller WorkspaceRecorder.spec
> ```

---

## 📁 專案目錄結構 (Project Structure)

```text
workspace-session-recorder/
├── src/                        # 原始程式碼
│   ├── __init__.py
│   ├── app.py                  # Tkinter GUI 主程式入口
│   ├── window_scanner.py       # 視窗列舉與程序資訊擷取（win32gui + psutil）
│   ├── browser_inspector.py    # 瀏覽器分頁網址擷取（UI Automation）
│   └── exporter.py             # .bat 批次檔產生與字元轉義邏輯
├── tests/                      # 單元測試（pytest）
│   ├── test_window_scanner.py
│   ├── test_browser_inspector.py
│   └── test_exporter.py
├── assets/                     # 圖示等靜態資源
├── requirements.txt            # 執行期依賴套件
├── requirements-dev.txt        # 開發 / 測試依賴套件
├── pytest.ini                  # pytest 設定檔
├── WorkspaceRecorder.spec      # PyInstaller 打包設定檔
├── LICENSE                     # 開源授權條款
└── README.md                   # 本說明文件
```

---

## 🧪 測試執行 (Testing)

本專案使用 [pytest](https://docs.pytest.org/) 撰寫單元測試，所有與 Windows API（`win32gui`、`psutil`、`uiautomation`）相關的呼叫皆以 Mock 方式模擬，測試執行時不會依賴實際系統狀態，也不需要真的開啟瀏覽器視窗。

### 安裝測試依賴

```powershell
pip install -r requirements-dev.txt
```

### 執行完整測試

```powershell
pytest
```

### 執行單一測試檔並顯示詳細結果

```powershell
pytest tests/test_exporter.py -v
```

---

## 📄 開源授權 (License)

本專案採用 [MIT License](./LICENSE) 授權條款釋出，歡迎自由使用、修改與散布，惟須保留原始版權聲明。

```text
MIT License

Copyright (c) 2026 ChungChiuHung

本軟體以「現狀」提供，不附帶任何明示或默示之擔保。
詳細條款請參閱專案根目錄下的 LICENSE 檔案。
```
