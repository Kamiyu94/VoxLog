# Windows 版 whisper.cpp 執行檔放這裡

VoxLog 的 whisper.cpp 引擎會**優先**用這個資料夾裡的執行檔，找不到才找系統 PATH。
把 Windows 的 `whisper-cli.exe` 連同它需要的 `*.dll` 放進這個資料夾後，
Windows 同事**只要 `git pull` 就能用 whisper.cpp，不必另外安裝、不必設 PATH**。

## 怎麼取得（在一台 Windows 機器上做一次）

1. 到 whisper.cpp 的 GitHub Releases：<https://github.com/ggml-org/whisper.cpp/releases>
2. 下載 **Windows x64 的預編譯包**（CPU 版即可，相容性最好；檔名類似 `whisper-bin-x64.zip`）。
3. 解壓後，把裡面的 **`whisper-cli.exe`** 和**同一層的所有 `*.dll`** 一起複製到本資料夾
   （`bin/whispercpp-win/`）。
4. 在該機器測一下能跑：開命令提示字元，`cd` 到本資料夾，執行
   `whisper-cli.exe --help`，有出說明就 OK。
5. 確認沒問題後 `git add bin/whispercpp-win/ && git commit && git push`，
   其他 Windows 同事 `git pull` 就自動有了。

## 注意
- whisper.cpp 採 MIT 授權，可合法隨專案散布。
- 模型檔（ggml-*.bin）**不要**放這裡——那個由程式第一次轉錄時自動下載到 `models/`。
- Mac 不需要這個資料夾，Mac 用 `brew install whisper-cpp` 即可。
