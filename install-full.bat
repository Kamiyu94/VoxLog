@echo off
chcp 65001 >nul
cd /d "%~dp0"
title VoxLog 完整版安裝
echo.
echo  ============================================
echo    VoxLog 完整版安裝（含 torch / 說話人辨識）
echo  ============================================
echo.
echo  [i] 含說話人辨識（誰說了哪句）。首次會下載約 2GB 的 torch；
echo      有 NVIDIA 顯卡會自動換成 CUDA 版加速。
echo.
REM 標記為完整版，交給 VoxLog.bat 完成安裝與啟動（邏輯只有一份，不重複維護）
set "VOXLOG_VARIANT=full"
call "%~dp0VoxLog.bat"
