#!/bin/zsh
# ============================================================
#  VoxLog 輕量版安裝（macOS / MacBook Air）
#  雙擊即可。做的事：
#    1. 確保有 Homebrew（沒有就裝）
#    2. 裝 python@3.11 + tkinter + FFmpeg + whisper.cpp
#    3. 用 Homebrew 的 python3.11 建乾淨的 venv
#    4. pip install -r requirements-lite.txt（不含 torch，省好幾 GB）
#    5. 登記 voxlog 指令
#  輕量版只做逐字稿 + AI 摘要，不含說話人辨識（那要完整版 install-full.command）。
# ============================================================
set -e
cd "${0:A:h}"   # 切到這支腳本真正所在的資料夾（解析掉 symlink）

echo "════════════════════════════════════════════"
echo "   VoxLog 輕量版安裝（whisper.cpp）"
echo "════════════════════════════════════════════"
echo ""

# 0) 提醒：非 git 版本之後無法用 update.command 一鍵更新
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
# 讓「這個」shell 立刻找得到 brew（Apple Silicon 在 /opt/homebrew、Intel 在 /usr/local）
[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
[[ -x /usr/local/bin/brew   ]] && eval "$(/usr/local/bin/brew shellenv)"

# 2) 系統依賴
echo "→ 安裝 Python 3.11 / tkinter / FFmpeg / whisper.cpp（已裝的會自動略過）…"
brew install python@3.11 python-tk@3.11 ffmpeg whisper-cpp

PY="$(brew --prefix)/bin/python3.11"

# 3) 乾淨的 venv（一定用 Homebrew 的 3.11，才不會踩系統 Python 的 Tcl/Tk 崩潰坑）
echo "→ 建立虛擬環境 venv …"
rm -rf venv
"$PY" -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip >/dev/null

# 4) 套件（輕量版）
echo "→ 安裝套件（輕量版，不含 torch）…"
pip install -r requirements-lite.txt

# 5) 登記 voxlog 全域指令（失敗不影響，之後仍可雙擊 voxlog 啟動）
chmod +x voxlog update.command 2>/dev/null || true
if [[ -w "$(brew --prefix)/bin" ]]; then
  ln -sf "$PWD/voxlog" "$(brew --prefix)/bin/voxlog" 2>/dev/null \
    && echo "→ 已登記指令：往後在終端機打 voxlog 也能啟動"
fi

echo ""
echo "✅ 安裝完成！"
echo "   ▸ 啟動：雙擊資料夾裡的「voxlog」"
echo "   ▸ 更新：雙擊「update.command」"
echo ""
echo "（可以關掉這個視窗了）"
