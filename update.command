#!/bin/zsh
# ============================================================
#  VoxLog 更新（macOS）—— 雙擊即可
#    1. git pull 取最新程式碼
#    2. 自動判斷你裝的是輕量版還完整版，補裝可能新增的套件
#  （API Key 設定、下載好的模型都不受影響，不會被覆蓋）
# ============================================================
set -e
cd "${0:A:h}"

echo "════════════════════════════════════════════"
echo "   VoxLog 更新"
echo "════════════════════════════════════════════"
echo ""

if [[ ! -d .git ]]; then
  echo "⚠  這不是 git 版本，無法自動更新。"
  echo "   請改用 git clone 的版本，或重新下載最新專案。"
  echo ""
  echo "（按 Enter 關閉）"
  read _
  exit 1
fi

echo "→ 取得最新版本（git pull）…"
git pull --ff-only

if [[ ! -d venv ]]; then
  echo ""
  echo "⚠  找不到 venv —— 你可能還沒安裝過。"
  echo "   請先雙擊 install-lite.command（或 install-full.command）。"
  echo ""
  echo "（按 Enter 關閉）"
  read _
  exit 1
fi

source venv/bin/activate

# 依 venv 裡有沒有 torch 判斷版本：有＝完整版、沒有＝輕量版
if python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('torch') else 1)"; then
  echo "→ 偵測到「完整版」，補裝 requirements.txt …"
  pip install -r requirements.txt
else
  echo "→ 偵測到「輕量版」，補裝 requirements-lite.txt …"
  pip install -r requirements-lite.txt
fi

echo ""
echo "✅ 更新完成！雙擊「voxlog」啟動即可。"
echo ""
echo "（可以關掉這個視窗了）"
