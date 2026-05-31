import whisper
import os

# Add ffmpeg to PATH
os.environ["PATH"] += r";C:\Users\kamiy\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"

audio_path = r"C:\Users\kamiy\OneDrive\文件\Dev\personal\Astrology\reference\4月30日 13-03.m4a"
output_path = r"C:\Users\kamiy\OneDrive\文件\Dev\personal\Astrology\reference\transcript.txt"

print("載入 Whisper medium 模型（首次需下載，約1.5GB）...")
model = whisper.load_model("medium")

print("開始轉錄，請稍候...")
result = model.transcribe(audio_path, language="zh", verbose=True)

with open(output_path, "w", encoding="utf-8") as f:
    f.write(result["text"])

print(f"\n完成！逐字稿已儲存至：{output_path}")
