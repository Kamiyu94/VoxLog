@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"
title VoxLog

echo.
echo  ==========================================
echo     VoxLog  -  語音轉文字 / AI 摘要工具
echo  ==========================================
echo.

REM ---------- 1. 偵測 Python ----------
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"

if not defined PY (
  echo  [X] 找不到 Python。
  echo.
  echo      請先安裝 Python 3.11 或 3.12，
  echo      安裝第一個畫面「務必勾選」: Add python.exe to PATH
  echo.
  echo      即將為你開啟官方下載頁...
  start "" https://www.python.org/downloads/
  echo      裝好後，重新雙擊本檔即可。
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo  [OK] 已偵測到 %%v

REM ---------- 2. 偵測 / 安裝 FFmpeg ----------
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo  [!] 找不到 FFmpeg，嘗試用 winget 自動安裝...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  echo  [i] FFmpeg 安裝完成（程式會自動尋找，不需另設定）
) else (
  echo  [OK] 已偵測到 FFmpeg
)

REM ---------- 3. 建立虛擬環境 ----------
if not exist "venv\Scripts\python.exe" (
  echo  [*] 第一次執行，建立虛擬環境 venv...
  %PY% -m venv venv
  if errorlevel 1 (
    echo  [X] 建立 venv 失敗。
    pause
    exit /b 1
  )
)

REM ---------- 4. 安裝套件（首次完整安裝；之後只在 requirements.txt 變動時自動補裝） ----------
set "NEED_INSTALL="
if not exist "venv\.voxlog_installed" set "NEED_INSTALL=1"
if not exist "venv\.voxlog_reqs" set "NEED_INSTALL=1"
if exist "venv\.voxlog_reqs" (
  fc /b requirements.txt "venv\.voxlog_reqs" >nul 2>nul || set "NEED_INSTALL=1"
)

if defined NEED_INSTALL (
  echo.
  echo  [*] 安裝/更新相依套件中... 首次含 torch 約 2GB，
  echo      網路要穩、請耐心等待（首次可能 10 分鐘以上，畫面沒動不是當機）。
  echo      更新時只會補裝新增的套件，很快。
  echo.
  "venv\Scripts\python.exe" -m pip install --upgrade pip
  "venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  [X] 套件安裝失敗，請檢查網路後再雙擊一次本檔重試。
    pause
    exit /b 1
  )
  echo installed> "venv\.voxlog_installed"
  copy /y requirements.txt "venv\.voxlog_reqs" >nul
  echo  [OK] 套件已就緒！
) else (
  echo  [OK] 套件已是最新，略過安裝步驟
)

REM ---------- 5. 註冊 voxlog 快速指令（之後任何終端機打 voxlog 就能啟動） ----------
REM WindowsApps 預設就在使用者 PATH 上，丟一個 voxlog.cmd 進去即可，免改 PATH。
set "SHIM_DIR=%LOCALAPPDATA%\Microsoft\WindowsApps"
set "SHIM=%SHIM_DIR%\voxlog.cmd"
set "SHIM_NEW="
if not exist "%SHIM%" set "SHIM_NEW=1"
if exist "%SHIM_DIR%\" (
  > "%SHIM%" echo @echo off
  >> "%SHIM%" echo call "%~dp0VoxLog.bat" %%*
  if defined SHIM_NEW echo  [OK] 已註冊 voxlog 指令：之後在「命令提示字元」或 PowerShell 打 voxlog 就能啟動
)

REM ---------- 6. 啟動主程式 ----------
echo.
echo  [*] 啟動 VoxLog...
echo.
"venv\Scripts\python.exe" transcribe_gui.py
if errorlevel 1 (
  echo.
  echo  [X] 程式異常結束，上方訊息為錯誤內容。
  pause
)

endlocal
