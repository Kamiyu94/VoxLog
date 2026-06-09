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

2. **pyannote.audio**：需要 HuggingFace Token（到 https://huggingface.co/settings/tokens
   建立，勾 Read access to public gated repositories），且需用同一帳號在 HF 網站接受使用條款：
   - https://huggingface.co/pyannote/speaker-diarization-community-1
   - https://huggingface.co/pyannote/segmentation-3.0

   > whisperx 的 `DiarizationPipeline` 預設載入 `speaker-diarization-community-1`
   > （見 `whisperx/diarize.py`），**不是**舊版 `3.1`；同意錯模型頁 token 會被擋。

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

## ⚠️ 第四個雷：AI API Key 驗證 401（同事 Gemini 實戰，已修文件 ✅）

按「驗證」出現 `HTTP 401: ... Expected OAuth 2 access token, login cookie or
other valid authentication credential`。

**關於金鑰格式（已查證，2026-06）**：Gemini API Key 有兩種合法開頭——
`AIza`（舊）與 `AQ.`（2026 新格式，部分帳號只發這種）。**兩者都能用 `?key=`
查詢參數打 `generativelanguage.googleapis.com/v1beta/models`**（已用真實 AQ key
實測：`?key=` 與 `x-goog-api-key:` 標頭兩種方法皆回 200）。所以 VoxLog 現行
`verify_engine` 用 `?key=`（transcribe_gui.py:272）**對 AQ key 沒問題，不需改**。
（`ya29.` / `GOCSPX-` / `4/` 開頭才是 OAuth token/密鑰/授權碼，非 API Key。）

> ⚠️ 早期誤判：一度以為 `AQ` 開頭不是有效 key——錯的，已更正。AQ 是 Google
> 2026 推的新金鑰格式。

**真正會 401 的原因**（key 格式正常下）：

1. **key 本身被擋**：金鑰被限制（HTTP referrer / IP 限制）、停用、所屬專案沒開
   Generative Language API，或 key 打錯/失效。判別法——拿該 key 直接 curl：
   `curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=KEY"`
   回 `"error"` → key 真有問題；回 `"models":[...]` → key 好，往下看次因。
2. **「瀏覽器有回應」≠ key 有效**：壞 key 也回 JSON，但內容是
   `{"error": {"code": 4xx, ...}}`。要看回的是 `"models"` 清單還是 `"error"`。
3. **次因——key 沒貼乾淨**：Key 欄位 `show="*"` 遮住，殘缺舊 key 沒清掉就貼 →
   新 key 累加在後面變壞字串。curl 同把 key 回 200、但 VoxLog 401，即屬此類。

**修法／繞過**：

```bash
# 確認 key 真的有效（看得到、跟 GUI 同樣的 REST 測法）
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=AIza開頭key" | head

# 繞過會累加的輸入框：直接寫進 config.json，App 啟動時自動載入（transcribe_gui.py:1090）
open -e config.json   # 把 "gemini_key" 換成確認過的 AIza key，存檔後重開
```

> 驗證端點打的是 `/models`（與模型無關），所以**就算之後 Gemini 退役某模型、驗證仍會綠**，
> 但實際產生摘要用的是某個模型名稱，退役後會 404。
> **已處理**：Claude / Gemini 的模型名稱已搬進 config.json（`claude_model` / `gemini_model`，
> 與 OpenAI 的 `openai_model` 一致），退役時改設定檔即可、免動程式。預設值仍寫在
> `_call_ai`（transcribe_gui.py），更新預設也只是改一個字串。

---

## ⚠️ 第五個雷：macOS 上 ⌘C/⌘V 在 GUI 失效（已內建修正）

tkinter 在 macOS 預設的 `Cmd+C/V/X/A` 常失靈，已由 `_enable_mac_clipboard()`
（transcribe_gui.py:1849）手動綁定修正。**舊下載版本沒有此修正**，需 `git pull`／
重抓 ZIP 後重啟。

> 已知殘留弱點：`Cmd+A` 靠 `event_generate("<<SelectAll>>")`，在 macOS Entry 上不一定生效，
> 導致「全選刪除」失敗、貼上變累加（即上面第四個雷的次因）。繞過法：直接編 config.json。

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

### 指定 AI 模型

**一般用 GUI 即可**：選好引擎後，下方「模型」下拉選單可直接點選；也能手動輸入
未列出的模型名稱。選完自動存進 config.json，不必手動編檔。

下拉的清單維護在 `transcribe_gui.py` 的 `_ENGINE_MODELS`，供應商新增/淘汰模型時
改那份清單再 `git pull` 即可。對應 config.json 欄位（手動編也可）：

```json
{
  "gemini_model": "gemini-3.1-flash-lite",
  "claude_model": "claude-sonnet-4-6",
  "openai_model": "gpt-4o"
}
```

> 不填則用程式內建預設。本地引擎（Ollama / LM Studio）的模型仍直接打在 Key 欄位。
