# VoxLog macOS 安裝進度

## 環境
- 機器：MacBook Pro M5（Mac17,2），32GB
- macOS：26.2 (25C56)
- 目標：將 VoxLog 從 Windows 移植到 macOS 上運行

---

## 遇到的問題

執行 `python3 transcribe_gui.py` 後，程式直接 crash（EXC_CRASH / SIGABRT）。

**根本原因**：使用了 Xcode Command Line Tools 內建的系統 Python 3.9，
該 Python 連結到 macOS 舊版系統 Tcl/Tk 8.5，在 macOS 26 上會崩潰。

```
問題 Python 路徑：
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/...

問題 Tcl/Tk 版本：8.5.9（太舊）
```

---

## 解法（已執行 ✅ 2026-06-02）

改用 Homebrew 安裝的 Python 3.11（帶自己的 Tcl/Tk 8.6）：

```bash
# 1. 安裝 Homebrew Python 和 tkinter 支援
brew install python@3.11 python-tk@3.11

# 2. 進到 VoxLog 資料夾，刪掉舊 venv，用正確 Python 重建
cd ~/VoxLog
rm -rf venv
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate

# 3. 安裝套件
pip install -r requirements.txt

# 4. 啟動
python transcribe_gui.py
```

---

## ⚠️ 安裝過程中額外踩到的雷：pyexpat / libexpat 符號不匹配（已修 ✅）

在第 2 步重建 venv 時，`python3.11 -m venv` 直接失敗，因為 Homebrew 的
python@3.11 (3.11.15_1) bottle 的 `pyexpat` 模組壞掉：

```
ImportError: dlopen(...pyexpat.cpython-311-darwin.so):
  Symbol not found: _XML_SetAllocTrackerActivationThreshold
  Expected in: /usr/lib/libexpat.1.dylib
```

**根本原因**：bottle 的 `pyexpat.so` 寫死連到 macOS 系統的
`/usr/lib/libexpat.1.dylib`，但 macOS 26.2 的系統 expat 沒有這個新符號；
而 Homebrew 自己的 `expat` 套件有（且預設沒被當成相依裝進來）。

**修法**：裝 Homebrew expat，把 `pyexpat.so` 改指向它，再重新簽章：

```bash
brew install expat

SO=/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/pyexpat.cpython-311-darwin.so
install_name_tool -change /usr/lib/libexpat.1.dylib /opt/homebrew/opt/expat/lib/libexpat.1.dylib "$SO"
codesign --force --sign - "$SO"

# 驗證
/opt/homebrew/bin/python3.11 -c "import pyexpat; print('pyexpat OK')"
```

> 注意：這個修補會在「升級 / 重裝 python@3.11」後失效，屆時需要重跑一次
> 上面的 install_name_tool + codesign（路徑中的版本號 3.11.15_1 要換成新版）。

---

## 完成解法後的預期後續問題

套件安裝過程中可能還會遇到：

1. **torch / whisperx**：M5 是 Apple Silicon，`pip install torch` 應自動裝 MPS 版。
   若 whisperx 安裝失敗，嘗試：
   ```bash
   pip install whisperx --no-deps
   pip install faster-whisper ctranslate2
   ```

2. **pyannote.audio**：需要 HuggingFace Token，且需要在 HF 網站接受使用條款：
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

3. **WhisperX 在 Mac 上只跑 CPU**：`whisperx_worker` 沒有 MPS 分支，
   速度比 Windows + CUDA 慢，功能正常。一般 Whisper 引擎有 MPS 支援，速度較快。

4. **opencc-python-reimplemented**：在 Apple Silicon 上有時需要從原始碼編譯：
   ```bash
   pip install opencc-python-reimplemented --no-binary :all:
   ```

---

## ⚠️ 第二個雷：torchcodec 不支援 ffmpeg 8（已修 ✅）

`import whisperx` / 跑語者分離時會看到 torchcodec 載入失敗的警告：

```
libtorchcodec_core7.dylib ... Library not loaded: @rpath/libavutil.59.dylib
```

**根本原因**：系統裝的是 ffmpeg 8.1.1（libavutil.60），但 `torchcodec 0.7.0`
只支援 ffmpeg 4–7（libavutil.56–59）。而 `pyannote.audio 4.0` 硬性依賴
torchcodec 來讀音訊（無 soundfile 後備），所以**語者分離會壞**。
（註：whisper / whisperx 的 `load_audio` 是直接呼叫 ffmpeg CLI，不受影響。）

**修法**：另外裝 ffmpeg@7（keg-only，不影響 ffmpeg 8 CLI），把它的函式庫
連結到 torchcodec 會搜尋的 `/opt/homebrew/lib`：

```bash
brew install ffmpeg@7

cd /opt/homebrew/lib
for lib in libavutil.59 libavcodec.61 libavformat.61 libavdevice.61 \
           libavfilter.10 libswscale.8 libswresample.5; do
  ln -sf "/opt/homebrew/opt/ffmpeg@7/lib/$lib.dylib" "$lib.dylib"
done

# 驗證
python -c "from torchcodec.decoders import AudioDecoder; print('OK')"
```

> 殘留的無害警告：`objc[...] Class AVFFrameReceiver is implemented in both ...`
> 這是 PyAV 內建的 libavdevice 跟 ffmpeg@7 的 libavdevice 重複註冊 AVFoundation
> 擷取裝置類別。VoxLog 只做檔案解碼、不碰即時擷取，所以可忽略。

---

## ✅ 安裝結果（2026-06-02 完成）

- venv：Python 3.11.15（Tcl/Tk 8.6），GUI 可正常啟動、不再 crash
- torch 2.8.0，**MPS 加速可用**
- 所有 requirements 套件 import 正常（含 torchcodec / pyannote.audio）
- ffmpeg：CLI 用 8.1.1；torchcodec 用 ffmpeg@7 函式庫

啟動指令：

```bash
cd ~/VoxLog
source venv/bin/activate
python transcribe_gui.py
```

---

## 目前程式碼的 macOS 相容性

| 項目 | 狀態 |
|------|------|
| FFmpeg 路徑（硬寫死 Windows 路徑） | ✅ 已有 `if platform.system() == "Windows"` 保護 |
| 字體設定 | ✅ macOS 自動用 `PingFang TC` |
| MPS 加速（Whisper） | ✅ 已支援 |
| MPS 加速（WhisperX） | ❌ 尚未支援，只跑 CPU |
| pyannote 語者分離（torchcodec + ffmpeg@7） | ✅ 已修可用 |
| GUI 啟動 | ✅ 已驗證可啟動，不再 crash |

---

## ⚠️ 第三個雷：brew 裝好了卻「command not found」（同事 M2 MBA 踩到，已修文件 ✅）

Apple Silicon Mac 裝完 Homebrew 後，`brew --version` 仍報 command not found。

**根本原因**：Homebrew 官方安裝程式在 Apple Silicon 上把 brew 裝在
`/opt/homebrew/`，但**不會自動把這路徑加進 PATH**；它只在安裝結尾「印出」
要手動補的兩行（`echo ... >> ~/.zprofile` + `eval ...`）。非工程師很容易
沒注意到、或關掉視窗就漏掉，導致「裝好了卻叫不動」。

**修法**：把 brew 的位置寫進 `~/.zprofile` 並在當前 session 立即生效：

```bash
echo >> ~/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# 驗證
brew --version   # 應跳出 Homebrew 5.x
```

> 診斷技巧：若 `brew --version` 沒反應，先用完整路徑 `/opt/homebrew/bin/brew --version`
> 測 —— 有版本號代表「已裝好、只是 PATH 沒接上」（跑上面那段即可）；
> 報 `no such file` 才是真的沒裝成功，要重跑安裝指令。
> （Intel Mac 路徑是 `/usr/local/bin/brew`，但本專案目標機器都是 Apple Silicon。）
>
> 已在 `MACOS_SETUP.html` 步驟 1 改為直接給固定指令，不再要使用者自己找那兩行。

---

## config.json 設定

從 Windows 複製 `config.json` 內容過來，或重新填寫：

```json
{
  "hf_token": "你的 HuggingFace Token",
  "gemini_key": "你的 Gemini API Key",
  "anthropic_key": "你的 Anthropic API Key",
  "lmstudio_model": "google/gemma-4-e4b",
  "cookies_browser": "Cookies: 無"
}
```
