#!/bin/zsh
# ============================================================
#  VoxLog 完整版安裝（macOS）
#  雙擊即可。含 torch / WhisperX / pyannote → 支援「說話人辨識」。
#  除了基本安裝，還會自動套用 Mac 上讓 pyannote 能跑的兩個修補
#  （對應 README 疑難排解 ② pyexpat、③ ffmpeg@7），使用者不用手動處理。
#
#  ⚠ 說話人辨識另外需要一個免費的 HuggingFace Token（見最後說明），
#     那步要在 VoxLog 介面裡貼上，無法在這自動完成。
# ============================================================
set -e
cd "${0:A:h}"

echo "════════════════════════════════════════════"
echo "   VoxLog 完整版安裝（含說話人辨識）"
echo "════════════════════════════════════════════"
echo ""

if [[ ! -d .git ]]; then
  echo "⚠  這個資料夾不是用 git 下載的，之後將無法用 update.command 一鍵更新。"
  echo "   建議改用 git clone 的版本。要繼續安裝請按 Enter，或直接關掉視窗。"
  read _
fi

# 1) Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "→ 未偵測到 Homebrew，開始安裝（過程中可能要你輸入這台電腦的密碼）…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
[[ -x /usr/local/bin/brew   ]] && eval "$(/usr/local/bin/brew shellenv)"

# 2) 系統依賴
echo "→ 安裝 Python 3.11 / tkinter / FFmpeg / whisper.cpp（已裝的會自動略過）…"
brew install python@3.11 python-tk@3.11 ffmpeg whisper-cpp

PY="$(brew --prefix)/bin/python3.11"

# 3) 乾淨的 venv
echo "→ 建立虛擬環境 venv …"
rm -rf venv
"$PY" -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip >/dev/null

# 4) 套件（完整版，含 torch，較大、時間較久）
echo "→ 安裝套件（完整版，含 torch / WhisperX / pyannote，這步會下載較多東西）…"
pip install -r requirements.txt

# ── Mac 專屬修補：讓 pyannote 說話人辨識不會崩 ──────────────────
echo "→ 套用 Mac 修補（pyexpat / ffmpeg@7），讓說話人辨識可用 …"
BREW="$(brew --prefix)"

# ② pyexpat：把 python3.11 的 pyexpat.so 改指向 Homebrew 的 expat 再重簽章
brew install expat >/dev/null 2>&1 || true
SO=$(ls "$BREW"/Cellar/python@3.11/*/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/pyexpat.cpython-311-darwin.so 2>/dev/null | head -1)
if [[ -n "$SO" ]]; then
  install_name_tool -change /usr/lib/libexpat.1.dylib "$BREW/opt/expat/lib/libexpat.1.dylib" "$SO" 2>/dev/null || true
  codesign --force --sign - "$SO" 2>/dev/null || true
fi

# ③ ffmpeg@7：torchcodec 只吃 FFmpeg 4–7，這裡把 7 的函式庫連進搜尋路徑（不影響 FFmpeg 8 CLI）
brew install ffmpeg@7 >/dev/null 2>&1 || true
F7="$BREW/opt/ffmpeg@7/lib"
if [[ -d "$F7" ]]; then
  for lib in libavutil.59 libavcodec.61 libavformat.61 libavdevice.61 \
             libavfilter.10 libswscale.8 libswresample.5; do
    [[ -e "$F7/$lib.dylib" ]] && ln -sf "$F7/$lib.dylib" "$BREW/lib/$lib.dylib"
  done
fi

# 5) 登記 voxlog 全域指令
chmod +x voxlog update.command 2>/dev/null || true
if [[ -w "$BREW/bin" ]]; then
  ln -sf "$PWD/voxlog" "$BREW/bin/voxlog" 2>/dev/null \
    && echo "→ 已登記指令：往後在終端機打 voxlog 也能啟動"
fi

echo ""
echo "✅ 安裝完成！"
echo "   ▸ 啟動：雙擊資料夾裡的「voxlog」"
echo "   ▸ 更新：雙擊「update.command」"
echo ""
echo "──────────────────────────────────────────────"
echo "  說話人辨識還差最後一步（免費、只做一次）："
echo "  1. 到 https://huggingface.co/settings/tokens 建一個 Token"
echo "     （勾 Read access to public gated repositories）"
echo "  2. 用同帳號到這兩頁各按一次 Agree and access repository："
echo "     https://huggingface.co/pyannote/speaker-diarization-community-1"
echo "     https://huggingface.co/pyannote/segmentation-3.0"
echo "  3. 打開 VoxLog，把 Token 貼進「HuggingFace Token」欄位。"
echo "──────────────────────────────────────────────"
echo ""
echo "（可以關掉這個視窗了）"
