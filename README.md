# VoxLog

VoxLog 是一個具備圖形化介面 (GUI) 的語音轉文字與 AI 輔助處理工具，能自動轉錄逐字稿、校正辨識錯誤、切割 SRT 字幕，以及利用 AI 自動產生會議紀錄與待辦事項。

## 系統需求
- Python 3.9 或以上版本
- FFmpeg（用於處理音訊與影片格式轉換）

## 安裝與設定說明

### 🍎 macOS

> ⚠️ **Mac 使用者請務必先讀本節最後的「macOS 注意事項 / 疑難排解」。**
> macOS 在這個 AI 語音專案上有幾個必踩的坑（系統內建 Python 會讓 GUI 崩潰、
> 部分套件與最新版 macOS / FFmpeg 不相容），照下面步驟可一次避開。

1. **下載專案與準備設定檔**
   ```bash
   git clone https://github.com/Kamiyu94/VoxLog.git
   cd VoxLog
   cp config.example.json config.json
   ```
   *(請打開 `config.json`，並將您的 API Keys 填入對應的欄位)*

2. **安裝 FFmpeg 與正確的 Python（重要）**
   ```bash
   # FFmpeg（CLI 用）
   brew install ffmpeg

   # ❗不要用 macOS 系統內建的 Python（會讓 GUI 崩潰，詳見疑難排解 ①）
   # 改裝 Homebrew 的 Python 與 tkinter 支援
   brew install python@3.11 python-tk@3.11
   ```

3. **建立虛擬環境並安裝套件**
   ```bash
   # ❗一定要用 Homebrew 的 python3.11 來建 venv
   rm -rf venv
   /opt/homebrew/bin/python3.11 -m venv venv
   source venv/bin/activate

   pip install -r requirements.txt

   # 啟動主程式
   python transcribe_gui.py
   ```
   *(若 `python3.11 -m venv` 失敗、或語者分離不能用，請看下方疑難排解 ② ③)*

---

### 🍎 macOS 注意事項 / 疑難排解

完整的安裝紀錄與指令在 [`MACOS_SETUP.md`](MACOS_SETUP.md)，這裡是重點摘要。

#### 為什麼 Mac 安裝比較麻煩？
本專案原本是 **Windows + NVIDIA(CUDA)** 環境開發的，移植到 Mac 會同時撞上三件事：
1. **Windows 優先開發** —— 版本搭配是照 Windows 調的。
2. **macOS 版本太新** —— Homebrew / torchcodec 等預編譯套件常跟不上最新 macOS 的系統函式庫，導致「找不到符號」之類的崩潰。
3. **重量級 AI 套件** —— torch / whisper / pyannote 對底層函式庫（FFmpeg、音訊解碼）非常挑剔。

這些坑**只有第一次安裝會踩**，解完就不會再遇到（除非之後升級相關套件，見最後一點）。

#### ① GUI 一啟動就 crash（EXC_CRASH / SIGABRT）
- **原因**：用到 macOS 系統內建 / Xcode CommandLineTools 的 Python 3.9，它連到太舊的系統 Tcl/Tk 8.5，在新版 macOS 上會崩潰。
- **解法**：改用 Homebrew 的 `python@3.11` + `python-tk@3.11`（自帶 Tcl/Tk 8.6），並用它重建 venv（見上方步驟 2、3）。

#### ② 連 venv 都建不起來（pyexpat / libexpat 符號錯誤）
症狀：`python3.11 -m venv` 失敗，或 `import pyexpat` 報
`Symbol not found: _XML_SetAllocTrackerActivationThreshold`。
- **原因**：Homebrew python bottle 的 `pyexpat` 連到 macOS 系統的 expat，但新系統的 expat 缺少該符號。
- **解法**：裝 Homebrew expat，把 `pyexpat.so` 改指向它再重簽章：
  ```bash
  brew install expat
  SO=/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/pyexpat.cpython-311-darwin.so
  install_name_tool -change /usr/lib/libexpat.1.dylib /opt/homebrew/opt/expat/lib/libexpat.1.dylib "$SO"
  codesign --force --sign - "$SO"
  ```
  *(路徑中的 `3.11.15_1` 要換成你實際安裝的版本號)*

#### ③ 語者分離（diarization）壞掉（torchcodec 找不到 libavutil）
症狀：`import whisperx` 出現 `libtorchcodec_core7.dylib ... Library not loaded: @rpath/libavutil.59.dylib`。
- **原因**：系統的 FFmpeg 是 8.x（libavutil.60），但 `torchcodec` 只支援 FFmpeg 4–7，而 `pyannote.audio` 硬性依賴 torchcodec 讀音訊。
  （一般 whisper / whisperx 轉錄是直接呼叫 FFmpeg CLI，不受影響；只有語者分離會壞。）
- **解法**：另外裝 `ffmpeg@7`（不影響 FFmpeg 8 CLI），把它的函式庫連到 torchcodec 的搜尋路徑：
  ```bash
  brew install ffmpeg@7
  cd /opt/homebrew/lib
  for lib in libavutil.59 libavcodec.61 libavformat.61 libavdevice.61 \
             libavfilter.10 libswscale.8 libswresample.5; do
    ln -sf "/opt/homebrew/opt/ffmpeg@7/lib/$lib.dylib" "$lib.dylib"
  done
  ```
  > 之後若看到 `objc[...] Class AVFFrameReceiver is implemented in both ...` 的警告可忽略，
  > 那只在使用即時擷取裝置時才會有影響，VoxLog 只做檔案解碼。

#### ④ 語者分離需要 HuggingFace Token + 接受模型條款
在 `config.json` 填入 `hf_token`，並到下列頁面用同一帳號按下「Agree / Accept」：
- https://huggingface.co/pyannote/speaker-diarization-3.1
- https://huggingface.co/pyannote/segmentation-3.0

#### ⑤ 效能與其他
- **Apple Silicon (M 系列)**：一般 Whisper 引擎支援 **MPS 加速**；WhisperX 目前在 Mac 只跑 CPU，功能正常但較慢。
- **⚠️ 升級後可能復發**：②、③ 是對 Homebrew 套件的手動修補，若日後執行 `brew upgrade`／重裝 `python@3.11` 或更新 `torchcodec`，可能需要**重做一次**對應步驟（路徑版本號記得更新）。

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
