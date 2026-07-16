@echo off
chcp 65001 >nul
cd /d "%~dp0"
title VoxLog 更新
echo.
echo  ============================================
echo    VoxLog 更新
echo  ============================================
echo.

REM ---------- 1. 需要是 git 版本才能自動更新 ----------
if not exist ".git" (
  echo  [X] 這不是 git 版本，無法自動更新。
  echo      請改用 git clone 的版本，或重新下載最新專案。
  echo.
  pause
  exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
  echo  [X] 找不到 git。請先安裝：winget install Git.Git
  echo      （或到 https://git-scm.com/download/win 下載）安裝後再試。
  echo.
  pause
  exit /b 1
)

REM ---------- 2. 取得最新程式碼 ----------
echo  [*] 取得最新版本（git pull）...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo  [X] git pull 失敗（可能你改過檔案、或沒有網路）。上方為錯誤內容。
  echo.
  pause
  exit /b 1
)

REM ---------- 3. 補裝套件（依 venv 記錄的版本） ----------
if not exist "venv\Scripts\python.exe" (
  echo.
  echo  [!] 還沒安裝過（找不到 venv）。請先雙擊 install-lite.bat 或 install-full.bat。
  echo.
  pause
  exit /b 1
)

set "VARIANT=full"
if exist "venv\.voxlog_variant" set /p VARIANT=<"venv\.voxlog_variant"
set "REQ=requirements.txt"
if /i "%VARIANT%"=="lite" set "REQ=requirements-lite.txt"

echo  [*] 版本：%VARIANT%，補裝 %REQ% ...
"venv\Scripts\python.exe" -m pip install -r "%REQ%"
if errorlevel 1 (
  echo.
  echo  [X] 套件安裝失敗，請檢查網路後再試一次。
  echo.
  pause
  exit /b 1
)

echo.
echo  [OK] 更新完成！雙擊 VoxLog.bat（或打 voxlog）啟動即可。
echo.
pause
