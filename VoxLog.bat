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

REM ---------- 0. 決定版本（輕量 lite / 完整 full）----------
REM   由 install-lite.bat / install-full.bat 透過 VOXLOG_VARIANT 指定；
REM   否則沿用 venv 內記錄；再否則預設完整版（向後相容既有安裝）。
if not defined VOXLOG_VARIANT if exist "venv\.voxlog_variant" set /p VOXLOG_VARIANT=<"venv\.voxlog_variant"
if not defined VOXLOG_VARIANT set "VOXLOG_VARIANT=full"
set "REQ=requirements.txt"
if /i "%VOXLOG_VARIANT%"=="lite" set "REQ=requirements-lite.txt"
echo  [i] 版本：%VOXLOG_VARIANT%（相依清單：%REQ%）
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

REM 記錄這個 venv 是輕量還完整版，之後啟動／更新都依此判斷（不會誤把 lite 灌成 full）
> "venv\.voxlog_variant" echo %VOXLOG_VARIANT%

REM ---------- 4. 安裝套件（首次完整安裝；之後只在 requirements.txt 變動時自動補裝） ----------
set "NEED_INSTALL="
if not exist "venv\.voxlog_installed" set "NEED_INSTALL=1"
if not exist "venv\.voxlog_reqs" set "NEED_INSTALL=1"
if exist "venv\.voxlog_reqs" (
  fc /b "%REQ%" "venv\.voxlog_reqs" >nul 2>nul || set "NEED_INSTALL=1"
)

if defined NEED_INSTALL (
  echo.
  echo  [*] 安裝/更新相依套件中...（完整版首次含 torch 約 2GB；輕量版不含 torch、快很多）
  echo      網路要穩、請耐心等待（完整版首次可能 10 分鐘以上，畫面沒動不是當機）。
  echo      更新時只會補裝新增的套件，很快。
  echo.
  "venv\Scripts\python.exe" -m pip install --upgrade pip
  "venv\Scripts\python.exe" -m pip install -r "%REQ%"
  if errorlevel 1 (
    echo.
    echo  [X] 套件安裝失敗，請檢查網路後再雙擊一次本檔重試。
    pause
    exit /b 1
  )
  echo installed> "venv\.voxlog_installed"
  copy /y "%REQ%" "venv\.voxlog_reqs" >nul
  echo  [OK] 套件已就緒！
) else (
  echo  [OK] 套件已是最新，略過安裝步驟
)

REM ---------- 5. NVIDIA GPU：自動換成 CUDA 版 torch（語音轉錄大幅加速） ----------
REM   requirements.txt 裝的是 CPU 版 torch（Windows 預設）。
REM   若偵測到 NVIDIA 顯卡，就換成 cu128 版；torch 已釘 2.8.0（WhisperX 相容版），
REM   cu128 同時支援 RTX 40 / 50 系列，舊卡也吃得到，故不需依顯卡分版本。
REM   輕量版不含 torch，直接略過。
if /i "%VOXLOG_VARIANT%"=="lite" goto skip_gpu
where nvidia-smi >nul 2>nul
if errorlevel 1 goto skip_gpu

"venv\Scripts\python.exe" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>nul
if not errorlevel 1 (
  echo  [OK] GPU 加速已啟用，無需重裝
  goto skip_gpu
)

echo.
echo  [*] 偵測到 NVIDIA 顯卡，但目前是 CPU 版 torch。
echo      換裝 CUDA（cu128）版以啟用 GPU 加速，約需重新下載 2~3GB...
echo.
"venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128

"venv\Scripts\python.exe" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [!] 換裝後仍偵測不到 GPU，多半是「NVIDIA 顯卡驅動太舊」。
  echo      請到 GeForce Experience 或 nvidia.com 更新驅動後，再雙擊一次本檔。
  echo      （程式現在仍可用，只是用 CPU 跑、較慢。）
) else (
  echo  [OK] GPU 加速已啟用（CUDA）
)

:skip_gpu

REM ---------- 6. 註冊 voxlog 快速指令（之後任何終端機打 voxlog 就能啟動） ----------
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

REM ---------- 7. 啟動主程式 ----------
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
