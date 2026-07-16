@echo off
chcp 65001 >nul
cd /d "%~dp0"
title VoxLog 輕量版安裝
echo.
echo  ============================================
echo    VoxLog 輕量版安裝（whisper.cpp，不含 torch）
echo  ============================================
echo.
echo  [i] 適合較低階 / 沒有獨立顯卡的機器：做逐字稿 + AI 摘要，
echo      省下約 2GB 的 torch。要「說話人辨識」請改用 install-full.bat。
echo.
REM 標記為輕量版，交給 VoxLog.bat 完成安裝與啟動（邏輯只有一份，不重複維護）
set "VOXLOG_VARIANT=lite"
call "%~dp0VoxLog.bat"
