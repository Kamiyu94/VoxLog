#!/bin/zsh
# ============================================================
#  VoxLog 打包（macOS，維護者用）
#  雙擊即可。從 GitHub 抓一份乾淨的原始碼，壓成可以直接放上
#  Google 雲端硬碟的 VoxLog.zip，存到「桌面」。
#
#  為什麼不直接壓本機資料夾？本機資料夾裡有 venv/、models/、
#  還有 config.json（裡面是 API 金鑰），壓進去等於把金鑰一起發出去。
#  這支腳本改成從 GitHub clone，只會拿到 git 追蹤的檔案。
#
#  ⚠ 因為是從 GitHub 抓，所以只包得到「已經 push 上去」的東西。
#     有未推送的 commit 時，下面會先提醒你。
# ============================================================
set -e
cd "${0:A:h}"

REPO="https://github.com/Kamiyu94/VoxLog.git"
DEST="$HOME/Desktop/VoxLog.zip"

echo "════════════════════════════════════════════"
echo "   VoxLog 打包（產生乾淨的 VoxLog.zip）"
echo "════════════════════════════════════════════"
echo ""

# 0) 前置檢查
if ! command -v git >/dev/null 2>&1; then
  echo "✗ 找不到 git，無法打包。請先安裝 Xcode 命令列工具：xcode-select --install"
  echo ""
  read -r _
  exit 1
fi

# 1) 本機有沒有還沒 push 的 commit？（包不到那些）
if [[ -d .git ]]; then
  echo "→ 檢查本機有沒有還沒推上 GitHub 的修改…"
  if git fetch origin main --quiet 2>/dev/null; then
    AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
    if [[ "$AHEAD" != "0" ]]; then
      echo ""
      echo "⚠  本機有 $AHEAD 個 commit 還沒 push，這些「不會」被打包進去："
      git log --oneline origin/main..HEAD | sed 's/^/     /'
      echo ""
      echo "   要先 push 的話請關掉這個視窗；確定照現在的 GitHub 版本打包就按 Enter。"
      read -r _
    else
      echo "  ✓ 本機與 GitHub 一致"
    fi
  else
    echo "  （連不上 GitHub，跳過這項檢查）"
  fi
fi

# 2) 在暫存資料夾抓一份乾淨的
WORK=$(mktemp -d /tmp/voxlog-pkg.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

echo "→ 從 GitHub 取得乾淨的原始碼…"
git clone --quiet "$REPO" "$WORK/VoxLog"

VERSION=$(cd "$WORK/VoxLog" && git log --oneline -1)
echo "  ✓ 版本：$VERSION"

# 3) 壓縮
#    用命令列的 zip -X，不要用 Finder 的「壓縮」——後者會夾帶一堆 __MACOSX/._ 垃圾檔。
#    make-zip.command 本身不必發給使用者，這裡排除掉。
echo "→ 壓縮中…"
( cd "$WORK" && zip -r -q -X VoxLog.zip VoxLog -x "VoxLog/make-zip.command" )

# 4) 驗貨：確認沒夾帶敏感檔、執行權限還在
echo "→ 檢查產出的 zip…"
LIST=$(unzip -l "$WORK/VoxLog.zip")
FAIL=0

if echo "$LIST" | grep -qE "VoxLog/config\.json|VoxLog/venv/|VoxLog/models/"; then
  echo "  ✗ 夾帶了不該有的檔案（config.json / venv / models），請勿上傳！"
  FAIL=1
else
  echo "  ✓ 沒有 config.json、venv、models"
fi

if echo "$LIST" | grep -q "__MACOSX"; then
  echo "  ✗ 夾帶了 __MACOSX 垃圾檔"
  FAIL=1
else
  echo "  ✓ 沒有 __MACOSX 垃圾檔"
fi

PERM=$(unzip -Z "$WORK/VoxLog.zip" "VoxLog/install-lite.command" 2>/dev/null | head -1)
if [[ "$PERM" == -rwx* ]]; then
  echo "  ✓ 安裝檔的執行權限有保留（雙擊有效）"
else
  echo "  ✗ 執行權限掉了，使用者雙擊安裝檔會沒反應"
  FAIL=1
fi

if echo "$LIST" | grep -q "VoxLog/\.git/"; then
  echo "  ✓ 含 .git（使用者裝完能用 update.command 一鍵更新）"
else
  echo "  ✗ 缺少 .git，使用者將無法一鍵更新"
  FAIL=1
fi

if [[ "$FAIL" != "0" ]]; then
  echo ""
  echo "✗ 檢查沒過，沒有輸出檔案。請把上面的訊息貼給我看。"
  echo ""
  read -r _
  exit 1
fi

# 5) 送到桌面
if [[ -e "$DEST" ]]; then
  mv -f "$DEST" "$HOME/Desktop/VoxLog-舊版.zip"
  echo "→ 桌面原本的 VoxLog.zip 已改名為「VoxLog-舊版.zip」"
fi
mv "$WORK/VoxLog.zip" "$DEST"

SIZE=$(du -h "$DEST" | cut -f1 | tr -d ' ')

echo ""
echo "✅ 完成！桌面上的 VoxLog.zip（$SIZE）"
echo ""
echo "──────────────────────────────────────────────"
echo "  接著上傳到 Google 雲端硬碟："
echo "  在雲端硬碟裡對舊的 VoxLog.zip 按右鍵 →「管理版本」"
echo "  →「上傳新版本」，選桌面這份。"
echo ""
echo "  ⚠ 不要刪掉舊檔再上傳新的——那樣連結會變，"
echo "     安裝網頁上的下載鈕就會失效。"
echo "──────────────────────────────────────────────"
echo ""

open -R "$DEST" 2>/dev/null || true
echo "（可以關掉這個視窗了）"
