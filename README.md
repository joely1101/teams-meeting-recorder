# 🎙️ Teams 會議雙向錄音 ＆ AI 語音轉文字工具 (Teams Meeting Recorder & AI Transcriber)

> 專為 Microsoft Teams、Google Meet、Zoom 等遠距視訊會議設計。一鍵同步擷取「揚聲器（對方聲音）」與「麥克風（自己聲音）」並高品質混音為 MP3，結合 Google Gemini AI 雲端模型快速生成精確時間軸、說話者角色識別逐字稿與重點會議摘要。

---

## 🌟 核心特色

1. **雙向音訊同步擷取與混音**
   - 採用 Windows WASAPI Loopback 底層音訊技術。
   - 同步擷取**電腦喇叭聲音**（對方的聲音）與**麥克風輸入**（自己的聲音），並提供即時音量動態條與獨立增益調節。
   - 支援將任一設備設為 `None`（可單錄對方或單錄自己）。
   - 音訊調整至零靜音或調整音量大小完全不影響錄音品質。
   - 雙軌即時軟體混音並直接輸出為標準 MP3 檔案。

2. **Gemini 雲端 AI 智慧語音轉文字**
   - 使用 Google Gemini Flash 雲端多模態大模型，長音訊支援自動分段與大檔案上傳。
   - 自動區分說話者角色（Speaker Diarization）並附加對話時間軸。
   - 自動生成結構化「會議重點摘要」與「待辦行動清單 (Action Items)」。
   - **自動分存二個檔案**：轉錄完成後於音訊同目錄自動產出 `*_會議摘要.txt` 與 `*_逐字稿.txt`。

3. **隱私與本機 API Key 安全機制**
   - 採用 Google 官方提供之免費額度 API Key（一般日常會議完全免付費）。
   - 介面提供「將 API Key 儲存在本機」勾選框：
     - **勾選**：每次開啟程式自動載入 API Key。
     - **取消勾選**：立即清除本地設定檔（`config.json`），維護公用電腦隱私安全。
   - 原始碼 repository 透過 `.gitignore` 嚴格過濾所有金鑰與個人會議錄音內容。

4. **電腦橫向寬螢幕現代化 UI ＆ 獨立單一 EXE 封裝**
   - 橫向雙欄排版：左欄雙向錄音控制台，右欄 AI 轉錄工作台與雙分頁摘要/逐字稿檢視。
   - 支援 PyInstaller 打包為單一可執行檔（`.exe`），在未安裝 Python 環境的電腦亦可雙擊即用。

---

## 🚀 快速上手 (Quick Start)

### 方式 A：直接運行 Python 原始碼

#### 1. 系統環境要求
- 作業系統：Windows 10 / Windows 11 (64-bit)
- Python 版本：Python 3.10 ~ 3.12

#### 2. 安裝相依套件
在終端機（PowerShell 或 CMD）中執行：
```bash
pip install -r requirements.txt
```

#### 3. 啟動應用程式
```bash
python recorder_gui.py
```
*(亦可雙擊 `啟動會議錄音器.bat` 或 `啟動會議錄音器(無黑窗).vbs` 快捷啟動)*

---

### 方式 B：自行編譯打包為單一 EXE 執行檔

若需要在其他未安裝 Python 的 Windows 電腦上運行，可使用 PyInstaller 封裝：
```bash
pyinstaller --noconfirm --onedir --windowed --name "Teams會議錄音與轉文字" --onefile recorder_gui.py
```
編譯完成後，執行檔將位於 `dist/Teams會議錄音與轉文字.exe`。

---

## 🔑 如何取得 Google Gemini API Key？

本工具的 AI 轉錄功能使用 Google 官方提供的 Gemini API，日常會議轉錄可完全使用**免費額度**：

1. 開啟瀏覽器造訪 [Google AI Studio 官網](https://aistudio.google.com/app/apikey)。
2. 使用平常的 Google (Gmail) 帳號登入。
3. 點選 **「Create API key」**（若第一次使用同意條款即可，並選擇在預設專案中建立）。
4. 複製產生的金鑰字串（以 `AIza...` 開頭），貼入本程式的「Google Gemini API Key」欄位中即可開始轉錄。

---

## 📁 專案架構

```text
├── audio_engine.py           # WASAPI Loopback 揚聲器與麥克風擷取、增益調節與 LAME MP3 混音引擎
├── transcriber.py            # Google Gemini 雲端語音轉文字模組（分拆摘要與逐字稿）
├── recorder_gui.py           # 橫向雙欄專業桌面 GUI 介面（Tkinter / ttk）
├── index.html                # 產品介紹與使用說明靜態展示網頁
├── requirements.txt          # Python 相依函式庫清單
├── config.json.example       # 設定檔範本（無任何金鑰）
├── 啟動會議錄音器.bat          # Windows 快捷啟動腳本
├── 啟動會議錄音器(無黑窗).vbs   # 背景無主控台黑窗快捷啟動腳本
└── .gitignore                # 敏感資訊（金鑰、錄音檔、逐字稿、二進位產物）排除規則
```

---

## 🔒 隱私與安全性 (Privacy & Security)

- 本工具之音訊處理（錄音與 MP3 混音）100% 在使用者電腦**本機端**完成。
- 僅在點擊「開始轉錄語音為文字」時，才會將該次錄音檔傳輸至 Google 官方 Gemini API 進行語音分析，無任何第三方伺服器中繼或保留您的會議對話。
- 本專案原始碼絕不包含任何個人 API Key 或敏感機密。

---

## 📄 授權條款 (License)

本專案採用 [MIT License](LICENSE) 授權條款開源釋出。歡迎自由使用、修改與二次開發。
