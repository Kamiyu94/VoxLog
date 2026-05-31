# VoxLog

VoxLog 是一個具備圖形化介面 (GUI) 的語音轉文字與 AI 輔助處理工具，能自動轉錄逐字稿、校正辨識錯誤、切割 SRT 字幕，以及利用 AI 自動產生會議紀錄與待辦事項。

## 系統需求
- Python 3.9 或以上版本
- FFmpeg（用於處理音訊與影片格式轉換）

## 安裝與設定說明

### 🍎 macOS
1. **下載專案與準備設定檔**
   ```bash
   git clone https://github.com/Kamiyu94/VoxLog.git
   cd VoxLog
   cp config.example.json config.json
   ```
   *(請打開 `config.json`，並將您的 API Keys 填入對應的欄位)*

2. **安裝 FFmpeg**
   Mac 環境下建議使用 Homebrew 安裝：
   ```bash
   brew install ffmpeg
   ```

3. **安裝 Python 依賴套件並執行**
   ```bash
   # 建立並啟動虛擬環境
   python3 -m venv venv
   source venv/bin/activate
   
   # 安裝套件
   pip install -r requirements.txt
   
   # 啟動主程式
   python3 transcribe_gui.py
   ```

---

### 🪟 Windows
1. **下載專案與準備設定檔**
   ```cmd
   git clone https://github.com/Kamiyu94/VoxLog.git
   cd VoxLog
   copy config.example.json config.json
   ```
   *(請打開 `config.json`，並將您的 API Keys 填入對應的欄位)*

2. **安裝 FFmpeg**
   如果尚未安裝，可透過 PowerShell 的 winget 指令安裝：
   ```powershell
   winget install "FFmpeg (Essentials Build)"
   ```
   *(註：若您已有其他 FFmpeg 環境，請確保它已加入系統的環境變數 PATH 中)*

3. **安裝 Python 依賴套件並執行**
   ```cmd
   # 建立並啟動虛擬環境
   python -m venv venv
   venv\Scripts\activate
   
   # 安裝套件
   pip install -r requirements.txt
   
   # 啟動主程式
   python transcribe_gui.py
   ```

## 其他文件
詳細的功能操作介紹與更進階的設定，請用瀏覽器開啟專案內的 `setup-guide.html` 查看完整操作手冊。
