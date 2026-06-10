import os
import re
import sys
import json
import time
import math
import platform
import threading
import subprocess
import multiprocessing
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if platform.system() == "Windows":
    # 把 winget 安裝的 ffmpeg 加進 PATH。原本寫死成特定使用者的路徑，
    # 換一台電腦（不同使用者名稱／ffmpeg 版本）就失效，這裡改成自動尋找。
    import glob
    _ff_pattern = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "bin",
    )
    for _d in glob.glob(_ff_pattern, recursive=True):
        if os.path.isfile(os.path.join(_d, "ffmpeg.exe")):
            os.environ["PATH"] += os.pathsep + _d
            break

FONT_UI = "Microsoft JhengHei" if platform.system() == "Windows" else "PingFang TC"

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

BG        = "#1E1E1E"
SURFACE   = "#2A2A2A"
BORDER    = "#3A3A3A"
TEXT      = "#E8E8E8"
SUBTEXT   = "#888888"
ACCENT    = "#4A9EFF"
GREEN     = "#27AE60"
GREEN_DIM = "#1A5C38"
RED       = "#E74C3C"
RED_HOVER = "#C0392B"
BLUE      = "#2471A3"
BLUE_DIM  = "#1A4F72"

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

LANG_MAP = {
    "中文": "zh",
    "英文": "en",
    "日文": "ja",
    "韓文": "ko",
    "自動偵測": None,
}

AI_SRT_PROMPT = """以下有 {n} 段逐字稿，每段以 ===SEG編號=== 標記開頭。
請將每段文字依語意切成適合字幕的短句，每句 15 字以內，以自然語意斷句。

輸出格式（嚴格遵守）：
- 每段用 ===SEG編號=== 開頭（與輸入編號對應）
- 短句各占一行
- 不要加任何其他內容、編號或符號

{segments}"""

CORRECT_PROMPT = """以下是一份語音辨識產生的逐字稿，可能含有空耳錯誤、同音異字或辨識錯誤。{context}
請修正明顯的辨識錯誤，規則如下：
- 保留所有說話人標記（如 SPEAKER_00：）和時間戳格式（如 [00:01 --> 00:21]）
- 不要增加、刪除或合併段落
- 不要改變說話內容的意思
- 以繁體中文輸出
- 直接輸出修正後的逐字稿，不要在前後加任何說明文字或前言

逐字稿內容：
{transcript}"""

NOTES_PROMPT = """以下是一份逐字稿（可能是會議、訪談或影片內容），請整理成結構化的摘要。{context}

逐字稿內容：
{transcript}

請輸出以下格式：
# 摘要

## 基本資訊
- 日期：
- 參與者：

## 重點摘要
（3-5個重點）

## 討論內容
（按主題整理，標記說話者）

## 決策事項
（本次討論確認的決定，若無則寫「無」）

## 待辦事項
| 負責人 | 事項 | 期限 |
|--------|------|------|

## 標籤

### 人物標籤
（列出影片中出現或被提到的人名，每個一行，格式：`#人名`；若無則寫「無」）

### 主題標籤
（3–5個主要主題，每個一行，格式：`#主題`）

### 議題標籤
（5–8個具體討論的議題或關鍵詞，每個一行，格式：`#議題`）

請用繁體中文輸出。"""


def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    cfg = load_config()
    cfg.update(data)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def ensure_config():
    """首次啟動若沒有 config.json，自動建立一份空白設定（金鑰留空、保留欄位與預設值），
    使用者完全不必手動建檔，直接在 GUI 填入金鑰按「驗證」即可存檔。"""
    if os.path.exists(CONFIG_PATH):
        return
    template = {}
    example_path = os.path.join(os.path.dirname(CONFIG_PATH), "config.example.json")
    try:
        with open(example_path, "r", encoding="utf-8") as f:
            example = json.load(f)
        for k, v in example.items():
            # placeholder（YOUR_xxx）清空，其餘預設值（如 openai_model）保留
            template[k] = "" if isinstance(v, str) and v.startswith("YOUR_") else v
    except Exception:
        template = {}
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_to_srt_segments(words, max_chars=20):
    """把逐字時間戳列表依標點/字數切成字幕段落，回傳 [(start, end, text), ...]。"""
    segments = []
    cur_words = []
    cur_text = ""
    for w in words:
        word = w.get("word", "").strip()
        if not word:
            continue
        cur_words.append(w)
        cur_text += word
        ends_sentence = any(c in word for c in "。！？")
        ends_clause = any(c in word for c in "，、") and len(cur_text) >= max_chars
        over_limit = len(cur_text) >= max_chars * 2  # 無標點強制切割
        if (ends_sentence or ends_clause or over_limit) and cur_words:
            segments.append((
                cur_words[0].get("start", 0),
                cur_words[-1].get("end", 0),
                cur_text,
            ))
            cur_words, cur_text = [], ""
    if cur_words:
        segments.append((
            cur_words[0].get("start", 0),
            cur_words[-1].get("end", 0),
            cur_text,
        ))
    return segments


def _call_ai(prompt, ai_engine, api_key):
    if ai_engine == "claude":
        import anthropic
        model = load_config().get("claude_model", "claude-sonnet-4-6")
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    elif ai_engine == "ollama":
        import requests
        model = api_key.strip() if api_key.strip() else "qwen2.5:7b"
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["response"]
    elif ai_engine == "lmstudio":
        import requests
        model = api_key.strip() if api_key.strip() else "google/gemma-4-e4b"
        resp = requests.post(
            "http://localhost:1234/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    elif ai_engine == "openai":
        from openai import OpenAI
        model = load_config().get("openai_model", "gpt-4o")
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    else:
        from google import genai
        model = load_config().get("gemini_model", "gemini-3.1-flash-lite")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text


# 各 AI 引擎在 config.json 對應的 key 欄位，以及顯示名稱
_ENGINE_CFG_KEY = {
    "claude": "anthropic_key",
    "gemini": "gemini_key",
    "openai": "openai_key",
    "ollama": "ollama_model",
    "lmstudio": "lmstudio_model",
}
_ENGINE_DISPLAY = {
    "claude": "Claude",
    "gemini": "Gemini",
    "openai": "OpenAI",
    "ollama": "Ollama",
    "lmstudio": "LM Studio",
}

# ── 雲端引擎可選的模型清單（GUI 下拉選單用）────────────────────────────
# 維護方式：供應商新增/淘汰模型時，改下面這份清單再 git pull 即可，毋須改其他程式。
# 使用者在 GUI 仍可手動輸入未列出的模型名稱。本地引擎（ollama / lmstudio）的模型
# 直接打在 Key 欄位，不走這份清單。
_ENGINE_MODELS = {
    "claude": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "gemini": ["gemini-3.1-flash-lite", "gemini-3.1-pro", "gemini-2.5-flash"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
}
# 各引擎的模型名稱在 config.json 對應的欄位（與 _call_ai 讀取的一致）
_ENGINE_MODEL_KEY = {
    "claude": "claude_model",
    "gemini": "gemini_model",
    "openai": "openai_model",
}
# 各引擎預設模型（與 _call_ai 的 fallback 一致；清單順序可不同，顯示以存檔值為準）
_ENGINE_MODEL_DEFAULT = {
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-3.1-flash-lite",
    "openai": "gpt-4o",
}


def verify_engine(ai_engine, api_key):
    """以最小成本的呼叫驗證金鑰／連線，回傳 (ok: bool, message: str)。"""
    if ai_engine == "claude":
        import anthropic
        anthropic.Anthropic(api_key=api_key).models.list(limit=1)
        return True, "Claude 金鑰有效"
    elif ai_engine == "openai":
        from openai import OpenAI
        OpenAI(api_key=api_key).models.list()
        return True, "OpenAI 金鑰有效"
    elif ai_engine == "gemini":
        # 直接打 REST：SDK 在金鑰被拒時只丟出誤導性的「client has been closed」，
        # 改用 REST 才能拿到「API key not valid」等可讀的真正原因。
        import requests
        r = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key}, timeout=15,
        )
        if r.status_code == 200:
            return True, "Gemini 金鑰有效"
        try:
            detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    elif ai_engine == "ollama":
        import requests
        requests.get("http://localhost:11434/api/tags", timeout=10).raise_for_status()
        return True, "Ollama 連線正常"
    elif ai_engine == "lmstudio":
        import requests
        requests.get("http://localhost:1234/v1/models", timeout=10).raise_for_status()
        return True, "LM Studio 連線正常"
    return False, "未知引擎"


_TXT_TS_PAT = re.compile(r'^\[(\d+):(\d+)\s*-->\s*(\d+):(\d+)\]\s*(.+)$')
_TXT_SPK_PAT = re.compile(r'^(.{1,40})：\s*$')


def txt_to_srt(transcript_path, out_path=None):
    if out_path is None:
        base = transcript_path.rsplit(".", 1)[0]
        for suffix in ("_transcript_corrected", "_transcript"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        out_path = base + ".srt"

    def _fmt(total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d},000"

    entries = []
    current_speaker = None
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            m = _TXT_TS_PAT.match(line)
            if m:
                sm, ss, em, es, text = m.groups()
                start = int(sm) * 60 + int(ss)
                end = int(em) * 60 + int(es)
                subtitle = text
                entries.append((_fmt(start), _fmt(end), subtitle))
            else:
                spk_m = _TXT_SPK_PAT.match(line)
                if spk_m and line.strip():
                    current_speaker = spk_m.group(1).strip()

    with open(out_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, 1):
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    return out_path


_SRT_TS_PAT = re.compile(
    r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)'
)


def _parse_srt(srt_path):
    """解析 SRT 檔，回傳 [(start_float, end_float, text), ...]。"""
    entries = []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    for block in re.split(r'\n\s*\n', content.strip()):
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            m = _SRT_TS_PAT.match(line.strip())
            if m:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = m.groups()
                start = int(h1)*3600 + int(m1)*60 + int(s1) + int(ms1)/1000
                end   = int(h2)*3600 + int(m2)*60 + int(s2) + int(ms2)/1000
                text  = " ".join(lines[i+1:]).strip()
                if text:
                    entries.append((start, end, text))
                break
    return entries


def _ai_cut_segments(segments, ai_engine, api_key):
    """一次 API call 批次切割所有長 segment，回傳新的 [(start, end, text), ...]。"""
    short = {}   # index → (start, end, text) 不需要切的
    long_idx = []  # 需要切的 segment index

    for i, (start, end, text) in enumerate(segments):
        if len(text) <= 15:
            short[i] = (start, end, text)
        else:
            long_idx.append(i)

    phrases_map = {}  # index → [phrase, ...]
    if long_idx:
        seg_blocks = "\n".join(
            f"===SEG{i}===（{int(segments[i][1] - segments[i][0])}秒）\n{segments[i][2]}"
            for i in long_idx
        )
        prompt = AI_SRT_PROMPT.format(n=len(long_idx), segments=seg_blocks)
        ai_out = _call_ai(prompt, ai_engine, api_key)

        current_idx = None
        for line in ai_out.splitlines():
            line = line.strip()
            m = re.match(r'^===SEG(\d+)===', line)
            if m:
                current_idx = int(m.group(1))
                phrases_map[current_idx] = []
            elif current_idx is not None and line:
                phrases_map[current_idx].append(line)

    result = []
    for i, (start, end, text) in enumerate(segments):
        if i in short:
            result.append((start, end, text))
            continue
        duration = end - start
        phrases = phrases_map.get(i, [])
        if not phrases:
            result.append((start, end, text))
            continue
        total_chars = sum(len(p) for p in phrases)
        t = start
        for j, phrase in enumerate(phrases):
            ratio = len(phrase) / total_chars if total_chars > 0 else 1.0 / len(phrases)
            phrase_end = t + duration * ratio if j < len(phrases) - 1 else end
            result.append((t, phrase_end, phrase))
            t = phrase_end
    return result


def _write_srt(entries, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(entries, 1):
            f.write(f"{i}\n{_format_srt_time(s)} --> {_format_srt_time(e)}\n{text}\n\n")


def txt_to_srt_ai(transcript_path, ai_engine, api_key, out_path=None):
    segments = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            m = _TXT_TS_PAT.match(line)
            if m:
                sm, ss, em, es, text = m.groups()
                segments.append((float(int(sm)*60 + int(ss)), float(int(em)*60 + int(es)), text.strip()))
    all_entries = _ai_cut_segments(segments, ai_engine, api_key)
    if out_path is None:
        base = transcript_path.rsplit(".", 1)[0]
        for suffix in ("_transcript_corrected", "_transcript"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        out_path = base + ".srt"
    _write_srt(all_entries, out_path)
    return out_path


def correct_transcript(transcript_path, ai_engine, api_key, out_path=None, context=""):
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()
    ctx = f"\n背景資訊：{context}" if context else ""
    corrected = _call_ai(CORRECT_PROMPT.format(context=ctx, transcript=transcript), ai_engine, api_key)
    if out_path is None:
        base = transcript_path.rsplit("_transcript", 1)[0]
        out_path = base + "_transcript_corrected.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(corrected)
    return out_path


def _open_file(path):
    """用系統預設程式開啟檔案（Mac / Windows / Linux 通用）。失敗不影響主流程。"""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


def _write_summary_docx(md_text, out_path):
    """把 AI 產出的 Markdown 摘要轉成 .docx（處理標題、清單、表格、**粗體**）。"""
    from docx import Document

    def add_runs(paragraph, text):
        # 行內 **粗體**：split 後奇數段就是粗體內容
        for idx, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
            if not part:
                continue
            run = paragraph.add_run(part)
            if idx % 2 == 1:
                run.bold = True

    doc = Document()
    lines = md_text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        # 表格：連續的 | ... | 行
        if stripped.startswith("|") and stripped.endswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                # 跳過分隔列 |---|---|
                if not all(c and set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                ncol = max(len(r) for r in rows)
                table = doc.add_table(rows=0, cols=ncol)
                table.style = "Table Grid"
                for r in rows:
                    tcells = table.add_row().cells
                    for j in range(ncol):
                        tcells[j].text = r[j] if j < len(r) else ""
            continue
        # 標題（必須是 # 後接空白；# 人名 標籤無空白，不會誤判）
        hm = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if hm:
            doc.add_heading(hm.group(2).strip(), level=min(len(hm.group(1)), 4))
            i += 1
            continue
        # 項目清單
        if stripped.startswith(("- ", "* ")):
            add_runs(doc.add_paragraph(style="List Bullet"), stripped[2:].strip())
            i += 1
            continue
        nm = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if nm:
            add_runs(doc.add_paragraph(style="List Number"), nm.group(2).strip())
            i += 1
            continue
        # 一般段落
        add_runs(doc.add_paragraph(), stripped)
        i += 1

    doc.save(out_path)


def generate_summary(transcript_path, ai_engine, api_key, out_path=None, context=""):
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()
    ctx = f"\n背景資訊：{context}" if context else ""
    notes = _call_ai(NOTES_PROMPT.format(context=ctx, transcript=transcript), ai_engine, api_key)
    if out_path is None:
        out_path = transcript_path.replace("_transcript.txt", "_摘要.docx")
        if out_path == transcript_path:
            out_path = transcript_path.rsplit(".", 1)[0] + "_摘要.docx"
    _write_summary_docx(notes, out_path)
    return out_path


class _StdoutCapture:
    _pat = re.compile(r'\[(\d+):(\d+\.\d+)')

    def __init__(self, duration, prog_q):
        self._duration = duration
        self._prog_q = prog_q
        self._buf = ""

    def write(self, text):
        self._buf += text
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            m = self._pat.search(line)
            if m and self._duration > 0:
                t = int(m.group(1)) * 60 + float(m.group(2))
                pct = min(int(t / self._duration * 100), 99)
                self._prog_q.put(pct)

    def flush(self):
        pass


def whisper_worker(audio, out_dir, model_name, lang, prompt, write_srt, result_q, log_q, prog_q):
    try:
        import whisper, torch, os, sys, platform
        if platform.system() == "Windows":
            os.environ["PATH"] += ";" + r"C:\Users\kamiy\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"

        if torch.cuda.is_available():
            device, gpu_name = "cuda", torch.cuda.get_device_name(0)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # Apple MPS 缺少 Whisper 用到的稀疏張量運算
            # (aten::_sparse_coo_tensor_with_dims_and_tensors / SparseMPS backend)，
            # 在 MPS 上轉錄會直接崩潰，因此 Mac 上的一般 Whisper 引擎改用 CPU。
            device, gpu_name = "cpu", "CPU（Mac 不支援 MPS 轉錄，已自動改用 CPU）"
        else:
            device, gpu_name = "cpu", "無"

        log_q.put(f"使用裝置：{device.upper()}（{gpu_name}）")
        log_q.put(f"載入模型：{model_name}")
        model = whisper.load_model(model_name, device=device)

        audio_data = whisper.load_audio(audio)
        duration = len(audio_data) / 16000
        m, s = int(duration // 60), int(duration % 60)
        log_q.put(f"開始轉錄：{os.path.basename(audio)}（{m} 分 {s} 秒）")

        sys.stdout = _StdoutCapture(duration, prog_q)
        result = model.transcribe(audio, language=lang, verbose=True,
                                  initial_prompt=prompt or None,
                                  word_timestamps=True)
        sys.stdout = sys.__stdout__
        prog_q.put(100)

        base = os.path.splitext(os.path.basename(audio))[0]
        out_path = os.path.join(out_dir, f"{base}_transcript.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            for seg in result["segments"]:
                start = int(seg["start"])
                end = int(seg["end"])
                ts = f"[{start//60:02d}:{start%60:02d} --> {end//60:02d}:{end%60:02d}]"
                f.write(f"{ts} {seg['text'].strip()}\n")

        if write_srt:
            srt_path = os.path.join(out_dir, f"{base}.srt")
            all_chunks = []
            for seg in result["segments"]:
                words = seg.get("words", [])
                if words:
                    all_chunks.extend(_words_to_srt_segments(words))
                else:
                    all_chunks.append((seg["start"], seg["end"], seg["text"].strip()))
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, (s, e, text) in enumerate(all_chunks, 1):
                    f.write(f"{i}\n{_format_srt_time(s)} --> {_format_srt_time(e)}\n{text}\n\n")
            log_q.put(f"字幕已輸出：{os.path.basename(srt_path)}")

        result_q.put(("done", out_path))
    except Exception as e:
        try:
            sys.stdout = sys.__stdout__
        except Exception:
            pass
        result_q.put(("error", str(e)))


def whisperx_worker(audio, out_dir, model_name, lang, hf_token, num_speakers, prompt, write_srt, result_q, log_q, prog_q):
    try:
        import whisperx, torch, os, platform
        if platform.system() == "Windows":
            os.environ["PATH"] += ";" + r"C:\Users\kamiy\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"

        if torch.cuda.is_available():
            device, compute_type, gpu_name = "cuda", "int8_float16", torch.cuda.get_device_name(0)
        else:
            device, compute_type, gpu_name = "cpu", "int8", "無（CPU）"

        log_q.put(f"使用裝置：{device.upper()}（{gpu_name}）")
        log_q.put(f"載入模型：{model_name}")

        model = whisperx.load_model(model_name, device, compute_type=compute_type)
        prog_q.put(10)

        audio_data = whisperx.load_audio(audio)
        duration = len(audio_data) / 16000
        m, s = int(duration // 60), int(duration % 60)
        log_q.put(f"開始轉錄：{os.path.basename(audio)}（{m} 分 {s} 秒）")

        transcribe_kwargs = {"batch_size": 8}
        if lang:
            transcribe_kwargs["language"] = lang
        result = model.transcribe(audio_data, **transcribe_kwargs)
        prog_q.put(40)

        detected_lang = result.get("language", lang or "zh")
        log_q.put("對齊時間戳...")
        model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=device)
        result = whisperx.align(result["segments"], model_a, metadata, audio_data, device,
                                return_char_alignments=False)
        prog_q.put(65)

        log_q.put("分析說話人...")
        from whisperx.diarize import DiarizationPipeline
        diarize_model = DiarizationPipeline(token=hf_token, device=device)
        diarize_kwargs = {}
        if num_speakers and num_speakers > 0:
            diarize_kwargs["num_speakers"] = num_speakers
        diarize_segments = diarize_model(audio_data, **diarize_kwargs)
        result = whisperx.assign_word_speakers(diarize_segments, result)
        prog_q.put(90)

        try:
            import opencc
            converter = opencc.OpenCC("s2twp")
        except Exception:
            converter = None

        base = os.path.splitext(os.path.basename(audio))[0]
        out_path = os.path.join(out_dir, f"{base}_transcript.txt")
        segments_for_srt = []
        with open(out_path, "w", encoding="utf-8") as f:
            current_speaker = None
            for seg in result["segments"]:
                start = seg.get("start", 0)
                end = seg.get("end", 0)
                speaker = seg.get("speaker", "SPEAKER_??")
                text = seg.get("text", "").strip()
                if not text:
                    continue
                if converter:
                    text = converter.convert(text)
                ts = f"[{int(start)//60:02d}:{int(start)%60:02d} --> {int(end)//60:02d}:{int(end)%60:02d}]"
                if speaker != current_speaker:
                    if current_speaker is not None:
                        f.write("\n")
                    f.write(f"{speaker}：\n")
                    current_speaker = speaker
                f.write(f"{ts} {text}\n")
                segments_for_srt.append((start, end, speaker, text))

        if write_srt:
            srt_path = os.path.join(out_dir, f"{base}.srt")
            all_chunks = []
            for seg in result["segments"]:
                speaker = seg.get("speaker", "")
                words = seg.get("words", [])
                if words:
                    for s, e, text in _words_to_srt_segments(words):
                        if converter:
                            text = converter.convert(text)
                        all_chunks.append((s, e, speaker, text))
                else:
                    text = seg.get("text", "").strip()
                    if converter:
                        text = converter.convert(text)
                    all_chunks.append((seg.get("start", 0), seg.get("end", 0), speaker, text))
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, (s, e, speaker, text) in enumerate(all_chunks, 1):
                    f.write(f"{i}\n{_format_srt_time(s)} --> {_format_srt_time(e)}\n{text}\n\n")
            log_q.put(f"字幕已輸出：{os.path.basename(srt_path)}")

        result_q.put(("done", out_path))
    except Exception as e:
        result_q.put(("error", str(e)))


def _make_icon():
    try:
        from PIL import Image, ImageDraw
        # 4× 超取樣後再縮小 → 線條與圓角都帶抗鋸齒，不再糊
        SS = 4
        size = 256
        S = size * SS
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # ── 圓角方形底（macOS 風格 squircle，帶垂直漸層）──
        radius = int(S * 0.22)
        bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg)
        top, bot = (44, 46, 52), (24, 24, 26)
        for y in range(S):
            t = y / S
            r = int(top[0] + (bot[0] - top[0]) * t)
            g = int(top[1] + (bot[1] - top[1]) * t)
            b = int(top[2] + (bot[2] - top[2]) * t)
            bg_draw.line([(0, y), (S, y)], fill=(r, g, b, 255))
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)
        img.paste(bg, (0, 0), mask)

        # ── 麥克風 ──
        cx     = S / 2
        accent = (74, 158, 255, 255)
        lw     = max(3, int(S * 0.046))
        half    = S * 0.115           # 麥克頭半寬
        cap_top = S * 0.20
        cap_bot = S * 0.48
        # 麥克頭（圓角膠囊）
        draw.rounded_rectangle(
            [cx - half, cap_top, cx + half, cap_bot],
            radius=half, fill=accent,
        )
        # U 形托架（弧，開口朝上讓麥克頭穿出）
        cy_cap = (cap_top + cap_bot) / 2
        r_arc  = half + S * 0.078
        draw.arc(
            [cx - r_arc, cy_cap - r_arc, cx + r_arc, cy_cap + r_arc],
            start=-20, end=200, fill=accent, width=lw,
        )
        # 支桿
        stem_top = cy_cap + r_arc
        base_y   = S * 0.77
        draw.line([(cx, stem_top), (cx, base_y)], fill=accent, width=lw)
        # 底座
        bw = S * 0.145
        draw.rounded_rectangle(
            [cx - bw, base_y - lw / 2, cx + bw, base_y + lw / 2],
            radius=lw / 2, fill=accent,
        )

        return img.resize((size, size), Image.LANCZOS)
    except Exception:
        return None


def _make_audio_icon(size=38):
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = size // 2, size // 2
        bar_w = max(2, size // 12)
        heights = [0.35, 0.6, 0.85, 1.0, 0.85, 0.6, 0.35]
        n = len(heights)
        gap = bar_w
        total = n * bar_w + (n - 1) * gap
        x0 = cx - total // 2
        color = (255, 255, 255, 210)
        for i, h in enumerate(heights):
            bh = int(size * h * 0.72)
            x = x0 + i * (bar_w + gap)
            y0_ = cy - bh // 2
            y1_ = cy + bh // 2
            draw.rounded_rectangle([x, y0_, x + bar_w, y1_], radius=bar_w // 2, fill=color)
        return img
    except Exception:
        return None


def _make_yt_icon(size=22):
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pad = 1
        rh = size // 3
        draw.rounded_rectangle(
            [pad, rh, size - pad, size - rh],
            radius=size // 7, fill=(204, 0, 0, 255),
        )
        cx, cy = size // 2, size // 2
        t = size // 5
        draw.polygon([(cx - t, cy - t), (cx + t + 1, cy), (cx - t, cy + t)], fill="white")
        return img
    except Exception:
        return None


class SpeakerNameDialog(ctk.CTkToplevel):
    def __init__(self, parent, speakers):
        super().__init__(parent)
        self.title("設定說話者名稱")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.grab_set()
        self.result = None
        self.entries = {}

        ctk.CTkLabel(
            self,
            text=f"辨識出 {len(speakers)} 位說話者，已填入預設名稱，可自行修改：",
            fg_color="transparent", text_color=TEXT,
            font=ctk.CTkFont(FONT_UI, 13),
        ).pack(anchor="w", padx=20, pady=(18, 10))

        for spk in speakers:
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row_frame, text=spk,
                         fg_color="transparent", text_color=SUBTEXT,
                         font=ctk.CTkFont(FONT_UI, 12),
                         width=110, anchor="e").pack(side="left", padx=(0, 10))
            var = tk.StringVar(value=spk)
            ctk.CTkEntry(row_frame, textvariable=var, width=200,
                         fg_color=SURFACE, text_color=TEXT,
                         border_color=BORDER, border_width=1,
                         font=ctk.CTkFont(FONT_UI, 12)).pack(side="left")
            self.entries[spk] = var

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(12, 18), padx=20, fill="x")
        ctk.CTkButton(btn_frame, text="確認", command=self._ok,
                      fg_color=GREEN, hover_color="#219A52",
                      text_color="white", width=90).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="略過", command=self._cancel,
                      fg_color=SURFACE, hover_color=BORDER,
                      text_color=TEXT, width=90).pack(side="right")
        self.transient(parent)
        self.wait_window()

    def _ok(self):
        self.result = {spk: (var.get().strip() or spk)
                       for spk, var in self.entries.items()}
        self.destroy()

    def _cancel(self):
        self.destroy()


MODEL_HELP_TEXT = (
    "模型越大越準，但越慢、越吃記憶體：\n"
    "• small（約 2GB）：快；安靜環境、標準國語就夠用\n"
    "• medium（約 5GB）：較準；扛得住口音、專有名詞、中英夾雜\n"
    "• large（約 10GB）：最準但最慢\n"
    "• tiny / base：最省資源，僅測試用\n\n"
    "8GB 記憶體的電腦請用 small；錯字可在下一步\n"
    "「AI 校正逐字稿」補回。"
)


class _Tooltip:
    """滑鼠移上去顯示說明的小浮窗（tkinter 沒內建，自己做一個）。"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() - 2
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        try:
            self.tip.attributes("-topmost", True)
        except Exception:
            pass
        # 外框用 BORDER、內層 SURFACE，做出細邊框效果
        outer = tk.Frame(self.tip, bg=BORDER)
        outer.pack()
        tk.Label(outer, text=self.text, justify="left",
                 bg=SURFACE, fg=TEXT, font=(FONT_UI, 15),
                 padx=14, pady=12).pack(padx=1, pady=1)

    def _hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class TranscribeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VoxLog")
        self.root.geometry("780x760")
        self.root.minsize(700, 620)
        self.root.configure(fg_color=BG)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)  # 分頁區撐開，log 維持固定小尺寸

        self.process = None
        self.result_q = None
        self.log_q = None
        self.prog_q = None
        self.timer_start = None
        self.timer_id = None
        self.transcript_path = None
        self.notes_thread = None
        self.ai_cancelled = False
        self._ai_anim_running = False
        self._ai_anim_val = 0.0
        self._ai_anim_dir = 1
        self.audio_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.srt_var = tk.BooleanVar(value=True)
        ensure_config()  # 首次啟動自動建立空白 config.json，小白不必手動建檔
        self.cfg = load_config()
        self.cookies_file_path = self.cfg.get("cookies_file_path", "")

        self._set_icon()
        self._build_ui()
        self.root.after(120, self._bring_to_front)

    def _bring_to_front(self):
        """啟動時把視窗帶到前景並取得焦點（macOS 上 python 跑的視窗預設不會搶前景）。"""
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:
            pass
        if platform.system() == "Darwin":
            try:
                from AppKit import NSApplication
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass

    def _set_icon(self):
        img = _make_icon()
        if img is None:
            return
        try:
            from PIL import ImageTk, Image
            self._icon_photos = [
                ImageTk.PhotoImage(img.resize((s, s), Image.LANCZOS))
                for s in [16, 32, 64, 128, 256]
            ]
            self.root.iconphoto(True, *self._icon_photos)
        except Exception:
            pass

        # macOS：iconphoto 吃不到 Dock，改用 NSApplication 直接設定 Dock 圖示
        if platform.system() == "Darwin":
            try:
                import io
                from AppKit import NSApplication, NSImage
                from Foundation import NSData
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
                ns_img = NSImage.alloc().initWithData_(data)
                NSApplication.sharedApplication().setApplicationIconImage_(ns_img)
            except Exception:
                pass

    # ── Section divider ────────────────────────────
    def _section_divider(self, row, text, pady=(14, 6)):
        frame = ctk.CTkFrame(self.root, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="we", padx=20, pady=pady)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        ctk.CTkFrame(frame, height=1, fg_color=BORDER).grid(
            row=0, column=0, sticky="we", padx=(0, 10), pady=7)
        ctk.CTkLabel(frame, text=text,
                     fg_color="transparent", text_color=SUBTEXT,
                     font=ctk.CTkFont(FONT_UI, 11)).grid(row=0, column=1)
        ctk.CTkFrame(frame, height=1, fg_color=BORDER).grid(
            row=0, column=2, sticky="we", padx=(10, 0), pady=7)

    # ── Build UI ───────────────────────────────────
    def _build_ui(self):
        F = ctk.CTkFont

        # ── 分頁：① 轉錄 / ② 逐字稿處理（加圖示讓分頁更醒目）──
        self._TAB_TRANSCRIBE = "🎙️  ①  轉錄逐字稿"
        self._TAB_AI = "📝  ②  逐字稿處理（AI 校正 / 摘要 / 字幕檔）"
        self.tabs = ctk.CTkTabview(
            self.root, fg_color=BG,
            segmented_button_fg_color=SURFACE,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT,
            segmented_button_unselected_color=SURFACE,
            segmented_button_unselected_hover_color=BORDER,
            text_color=TEXT,
        )
        self.tabs.grid(row=0, column=0, sticky="nswe", padx=16, pady=(10, 2))
        # 放大分頁按鈕，讓使用者清楚看到目前在哪一頁
        try:
            self.tabs._segmented_button.configure(font=F(FONT_UI, 16, weight="bold"), height=40)
        except Exception:
            pass
        tab_t = self.tabs.add(self._TAB_TRANSCRIBE)
        tab_ai = self.tabs.add(self._TAB_AI)

        # ════════ 分頁一：轉錄 ════════
        ctk.CTkLabel(
            tab_t, justify="left",
            text="① 選音檔或貼 YouTube 網址　② 設好輸出資料夾　③ 按「開始轉錄」",
            fg_color="transparent", text_color=TEXT, font=F(FONT_UI, 16),
        ).pack(anchor="w", padx=4, pady=(14, 10))

        # 設定（轉錄模型 / 語言 / 轉錄引擎）
        settings = ctk.CTkFrame(tab_t, fg_color=SURFACE, corner_radius=8)
        settings.pack(fill="x", pady=(0, 4), ipady=6)

        ctk.CTkLabel(settings, text="轉錄模型", fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 14)).pack(side="left", padx=(14, 4))
        self.model_var = tk.StringVar(value="small")
        ctk.CTkComboBox(settings, variable=self.model_var,
                        values=["tiny", "base", "small", "medium", "large"],
                        width=104, state="readonly",
                        fg_color=BG, text_color=TEXT, button_color=BORDER,
                        button_hover_color=ACCENT, border_color=BORDER,
                        dropdown_fg_color=SURFACE, dropdown_text_color=TEXT,
                        dropdown_hover_color=BORDER,
                        font=F(FONT_UI, 13)).pack(side="left")
        model_info = ctk.CTkLabel(settings, text="ⓘ", fg_color="transparent",
                                   text_color=ACCENT, font=F(FONT_UI, 15), cursor="hand2")
        model_info.pack(side="left", padx=(4, 0))
        _Tooltip(model_info, MODEL_HELP_TEXT)

        ctk.CTkLabel(settings, text="語言", fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 14)).pack(side="left", padx=(16, 4))
        self.lang_var = tk.StringVar(value="中文")
        ctk.CTkComboBox(settings, variable=self.lang_var,
                        values=list(LANG_MAP.keys()),
                        width=110, state="readonly",
                        fg_color=BG, text_color=TEXT, button_color=BORDER,
                        button_hover_color=ACCENT, border_color=BORDER,
                        dropdown_fg_color=SURFACE, dropdown_text_color=TEXT,
                        dropdown_hover_color=BORDER,
                        font=F(FONT_UI, 13)).pack(side="left")

        ctk.CTkLabel(settings, text="轉錄引擎", fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 14)).pack(side="left", padx=(18, 6))
        self.engine_var = tk.StringVar(value="whisper")
        for val, label in [("whisper", "Whisper"), ("whisperx", "WhisperX（說話人辨識）")]:
            ctk.CTkRadioButton(
                settings, text=label, variable=self.engine_var,
                value=val, command=self._on_engine_change,
                text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT,
                font=F(FONT_UI, 14),
            ).pack(side="left", padx=(0, 10))

        # 來源選擇（兩個方形按鈕，置中）
        source = ctk.CTkFrame(tab_t, fg_color="transparent")
        source.pack(pady=(14, 6))

        audio_col = ctk.CTkFrame(source, fg_color="transparent")
        audio_col.pack(side="left", padx=28, anchor="n")
        audio_img = _make_audio_icon(40)
        self._audio_icon = ctk.CTkImage(
            light_image=audio_img, dark_image=audio_img, size=(40, 40)
        ) if audio_img else None
        ctk.CTkButton(
            audio_col, text="選擇音/影檔", image=self._audio_icon, compound="top",
            command=self.pick_audio,
            fg_color=ACCENT, hover_color="#2980B9", text_color="white",
            font=F(FONT_UI, 15, weight="bold"), width=165, height=110,
        ).pack()
        self.audio_display_var = tk.StringVar(value="未選擇")
        ctk.CTkLabel(audio_col, textvariable=self.audio_display_var,
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 12), width=165, anchor="center").pack(pady=(6, 0))

        yt_col = ctk.CTkFrame(source, fg_color="transparent")
        yt_col.pack(side="left", padx=28, anchor="n")
        yt_img = _make_yt_icon(40)
        self._yt_icon = ctk.CTkImage(
            light_image=yt_img, dark_image=yt_img, size=(40, 40)
        ) if yt_img else None
        self.yt_btn = ctk.CTkButton(
            yt_col, text="YouTube下載", image=self._yt_icon, compound="top",
            command=self.download_youtube,
            fg_color="#CC0000", hover_color="#990000", text_color="white",
            font=F(FONT_UI, 15, weight="bold"), width=165, height=110,
        )
        self.yt_btn.pack()
        self.yt_url_var = tk.StringVar()
        ctk.CTkEntry(
            yt_col, textvariable=self.yt_url_var,
            placeholder_text="貼上 YouTube 網址…",
            fg_color=SURFACE, text_color=TEXT,
            border_color=BORDER, border_width=1,
            font=F(FONT_UI, 12), width=336, height=32,
        ).pack(pady=(6, 0))
        self.cookies_browser_var = tk.StringVar(value=self.cfg.get("cookies_browser", "Cookies: 無"))
        ctk.CTkComboBox(
            yt_col, variable=self.cookies_browser_var,
            values=["Cookies: 無", "Cookies: Chrome", "Cookies: Edge", "Cookies: Firefox", "Cookies: Brave", "Cookies: Opera", "Cookies: Safari", "Cookies: 檔案", "Cookies: 選擇檔案..."],
            width=336, state="readonly",
            command=self._on_cookies_change,
            fg_color=SURFACE, text_color=TEXT, button_color=BORDER,
            button_hover_color=ACCENT, border_color=BORDER,
            dropdown_fg_color=SURFACE, dropdown_text_color=TEXT,
            dropdown_hover_color=BORDER,
            font=F(FONT_UI, 12)
        ).pack(pady=(6, 0))

        # WhisperX 選項（預設隱藏，選 WhisperX 才 pack 出來）
        self.wx_frame = ctk.CTkFrame(tab_t, fg_color="transparent")

        ctk.CTkLabel(self.wx_frame, text="HF Token",
                     fg_color="transparent", text_color=TEXT,
                     font=F(FONT_UI, 14), width=80, anchor="e").pack(side="left", padx=(0, 8))
        self.token_var = tk.StringVar(value=self.cfg.get("hf_token", ""))
        ctk.CTkEntry(self.wx_frame, textvariable=self.token_var, width=280, show="*",
                     fg_color=SURFACE, text_color=TEXT,
                     border_color=BORDER, border_width=1,
                     font=F(FONT_UI, 13)).pack(side="left", padx=(0, 16))
        ctk.CTkLabel(self.wx_frame, text="說話人數",
                     fg_color="transparent", text_color=TEXT,
                     font=F(FONT_UI, 14)).pack(side="left", padx=(0, 6))
        self.speakers_var = tk.IntVar(value=0)
        tk.Spinbox(self.wx_frame, from_=0, to=10, textvariable=self.speakers_var,
                   width=4, bg=SURFACE, fg=TEXT, buttonbackground=BORDER,
                   relief="flat", font=(FONT_UI, 13),
                   highlightthickness=1, highlightbackground=BORDER).pack(side="left")
        ctk.CTkLabel(self.wx_frame, text="（0 ＝ 自動）",
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 13)).pack(side="left", padx=(6, 0))

        # 輸出 + 情境說明
        r_out = ctk.CTkFrame(tab_t, fg_color="transparent")
        self.r_out = r_out
        r_out.pack(fill="x", pady=4)

        self.prompt_var = tk.StringVar(value="以下是繁體中文對話。")
        ctk.CTkEntry(r_out, textvariable=self.prompt_var,
                     fg_color=SURFACE, text_color=TEXT,
                     border_color=BORDER, border_width=1,
                     font=F(FONT_UI, 13)).pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(r_out, text="情境說明",
                     fg_color="transparent", text_color=TEXT,
                     font=F(FONT_UI, 14)).pack(side="right", padx=(20, 6))
        ctk.CTkButton(r_out, text="輸出資料夾", command=self.pick_output,
                      fg_color=SURFACE, hover_color=BORDER, text_color=TEXT,
                      font=F(FONT_UI, 14), width=110).pack(side="left")
        self.out_display_var = tk.StringVar(value="未選擇")
        ctk.CTkLabel(r_out, textvariable=self.out_display_var,
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 13), anchor="w",
                     width=180).pack(side="left", padx=(10, 0))
        ctk.CTkCheckBox(r_out, text="輸出字幕 SRT", variable=self.srt_var,
                        fg_color=ACCENT, hover_color="#2980B9",
                        text_color=TEXT, font=F(FONT_UI, 13),
                        ).pack(side="left", padx=(12, 0))

        # ▶ 開始轉錄 / ■ 停止
        trans_ctrl = ctk.CTkFrame(tab_t, fg_color="transparent")
        trans_ctrl.pack(pady=(10, 8))
        self.start_btn = ctk.CTkButton(
            trans_ctrl, text="▶  開始轉錄", command=self.start,
            fg_color=GREEN, hover_color="#219A52", text_color="white",
            font=F(FONT_UI, 16, weight="bold"), width=140, height=48,
        )
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = ctk.CTkButton(
            trans_ctrl, text="■  停止", command=self.stop,
            fg_color=RED, hover_color=RED_HOVER, text_color="white",
            font=F(FONT_UI, 16, weight="bold"), width=110, height=48,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=10)

        # ════════ 分頁二：AI 後製 ════════
        ctk.CTkLabel(
            tab_ai, justify="left",
            text="轉錄完成會自動帶你到這頁；也可直接按下方「載入逐字稿」處理舊檔。\n"
                 "① 選 AI 引擎　② 填 API Key 按「驗證」變綠　③ 點「校正逐字稿 / 產生摘要 / 匯出 SRT」",
            fg_color="transparent", text_color=TEXT, font=F(FONT_UI, 16),
        ).pack(anchor="w", padx=4, pady=(14, 12))

        ai_frame = ctk.CTkFrame(tab_ai, fg_color="transparent")
        ai_frame.pack(fill="x", pady=(0, 4))

        # 第一行：AI 引擎選擇
        ai_engine_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
        ai_engine_row.pack(fill="x", anchor="w")
        ctk.CTkLabel(ai_engine_row, text="AI 引擎",
                     fg_color="transparent", text_color=TEXT,
                     font=F(FONT_UI, 14), width=72, anchor="e").pack(side="left", padx=(0, 8))
        self.ai_engine_var = tk.StringVar(value="gemini")
        for val, label in [("claude", "Claude"), ("gemini", "Gemini"), ("openai", "ChatGPT"), ("ollama", "Ollama"), ("lmstudio", "LM Studio")]:
            ctk.CTkRadioButton(
                ai_engine_row, text=label, variable=self.ai_engine_var,
                value=val, command=self._on_ai_engine_change,
                text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT,
                font=F(FONT_UI, 14),
            ).pack(side="left", padx=(0, 12))

        # 第二行：模型選擇（雲端引擎才顯示；可下拉點選，也可手動輸入）
        self.ai_model_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
        ctk.CTkLabel(self.ai_model_row, text="AI 模型",
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 13), width=72, anchor="e").pack(side="left", padx=(0, 8))
        self.ai_model_var = tk.StringVar(
            value=self.cfg.get("gemini_model", _ENGINE_MODEL_DEFAULT["gemini"]))
        self.ai_model_combo = ctk.CTkComboBox(
            self.ai_model_row, variable=self.ai_model_var, values=_ENGINE_MODELS["gemini"],
            width=260,
            fg_color=SURFACE, text_color=TEXT, border_color=BORDER, border_width=1,
            button_color=BORDER, button_hover_color=ACCENT,
            dropdown_fg_color=SURFACE, dropdown_text_color=TEXT, dropdown_hover_color=BORDER,
            font=F(FONT_UI, 13),
        )
        self.ai_model_combo.pack(side="left", padx=(0, 4))
        self.ai_model_row.pack(fill="x", anchor="w", pady=(6, 0))

        # 第三行：API Key 輸入
        self.ai_key_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
        self.ai_key_row.pack(fill="x", anchor="w", pady=(6, 0))
        self.ai_key_label = ctk.CTkLabel(self.ai_key_row, text="Gemini Key",
                                          fg_color="transparent", text_color=SUBTEXT,
                                          font=F(FONT_UI, 13), width=72, anchor="e")
        self.ai_key_label.pack(side="left", padx=(0, 8))
        self.ai_key_var = tk.StringVar(value=self.cfg.get("gemini_key", ""))
        self.verify_btn = ctk.CTkButton(
            self.ai_key_row, text="驗證", command=self._verify_api,
            font=F(FONT_UI, 13, weight="bold"), width=64,
        )
        self.verify_btn.pack(side="right", padx=(8, 0))
        self.ai_key_entry = ctk.CTkEntry(self.ai_key_row, textvariable=self.ai_key_var, show="*",
                                         fg_color=SURFACE, text_color=TEXT,
                                         border_color=BORDER, border_width=1,
                                         font=F(FONT_UI, 13))
        self.ai_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        # 有填入值時才把「驗證」鈕從暗色轉成藍色，明確提示可按
        self.ai_key_var.trace_add("write", self._update_verify_btn)
        self._update_verify_btn()
        # 模型下拉變動（點選或手打）即存進 config，並依目前引擎同步顯示
        self.ai_model_var.trace_add("write", self._on_model_change)
        self._sync_model_widget(self.ai_engine_var.get())

        # 後製按鈕
        post_outer = ctk.CTkFrame(tab_ai, fg_color="transparent")
        post_outer.pack(pady=(10, 4))
        post_row = ctk.CTkFrame(post_outer, fg_color="transparent")
        post_row.pack()
        self.load_btn = ctk.CTkButton(
            post_row, text="載入逐字稿", command=self.load_transcript,
            fg_color=SURFACE, hover_color=BORDER, text_color=TEXT,
            font=F(FONT_UI, 14), width=130,
        )
        self.load_btn.pack(side="left", padx=8)
        self.correct_btn = ctk.CTkButton(
            post_row, text="校正逐字稿", command=self.correct_transcript,
            fg_color=BLUE_DIM, hover_color=BLUE, text_color=SUBTEXT,
            font=F(FONT_UI, 14), width=130, state="disabled",
        )
        self.correct_btn.pack(side="left", padx=8)
        self.notes_btn = ctk.CTkButton(
            post_row, text="產生摘要", command=self.generate_notes,
            fg_color=BLUE_DIM, hover_color=BLUE, text_color=SUBTEXT,
            font=F(FONT_UI, 14), width=120, state="disabled",
        )
        self.notes_btn.pack(side="left", padx=8)
        self.export_srt_btn = ctk.CTkButton(
            post_row, text="匯出 SRT", command=self.export_srt,
            fg_color=BLUE_DIM, hover_color=BLUE, text_color=SUBTEXT,
            font=F(FONT_UI, 14), width=110, state="disabled",
        )
        self.export_srt_btn.pack(side="left", padx=8)
        self.loaded_file_var = tk.StringVar(value="")
        ctk.CTkLabel(post_outer, textvariable=self.loaded_file_var,
                     fg_color="transparent", text_color=ACCENT,
                     font=F(FONT_UI, 12)).pack(pady=(4, 0))

        # ════════ 共用底部：計時 / 狀態 / 進度 / Log（兩個分頁都看得到）════════
        # 計時器 + 百分比
        info_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        info_frame.grid(row=1, column=0, pady=(8, 2))
        self.timer_var = tk.StringVar(value="00:00:00")
        ctk.CTkLabel(info_frame, textvariable=self.timer_var,
                     fg_color="transparent", text_color=ACCENT,
                     font=F("Consolas", 22, weight="bold")).pack(side="left", padx=(0, 16))
        self.pct_var = tk.StringVar(value="")
        ctk.CTkLabel(info_frame, textvariable=self.pct_var,
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 16)).pack(side="left")

        # 狀態
        self.status_label = ctk.CTkLabel(
            self.root, text="等待中...",
            fg_color="transparent", text_color=SUBTEXT,
            font=F(FONT_UI, 15, weight="bold"),
        )
        self.status_label.grid(row=2, column=0)

        # 進度條
        self.progress = ctk.CTkProgressBar(
            self.root, mode="determinate",
            fg_color=SURFACE, progress_color=ACCENT,
        )
        self.progress.set(0)
        self.progress.grid(row=3, column=0, padx=20, pady=6, sticky="we")

        # Log header
        log_hdr = ctk.CTkFrame(self.root, fg_color="transparent")
        log_hdr.grid(row=4, column=0, sticky="we", padx=20, pady=(4, 0))
        log_hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(log_hdr, text="Log",
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 12)).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(log_hdr, text="Kamiyu Lab",
                     fg_color="transparent", text_color=SUBTEXT,
                     font=F(FONT_UI, 13)).grid(row=0, column=2, sticky="e")

        # Log（固定小尺寸，不再吃掉版面）
        self.log = ctk.CTkTextbox(
            self.root,
            fg_color=SURFACE, text_color=TEXT,
            font=F("Consolas", 13),
            height=112,
            state="disabled",
        )
        self.log.grid(row=5, column=0, padx=20, pady=(2, 12), sticky="we")

    # ── YouTube 下載 ───────────────────────────────
    def download_youtube(self):
        url = self.yt_url_var.get().strip()
        if not url:
            self._set_status("請輸入 YouTube 網址", RED)
            return
        out_dir = self.out_var.get().strip()
        if not out_dir:
            out_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            self.out_var.set(out_dir)
            self.out_display_var.set(out_dir)

        browser_selected = self.cookies_browser_var.get()
        save_config({"cookies_browser": browser_selected})
        self.cfg["cookies_browser"] = browser_selected

        self.yt_btn.configure(state="disabled")
        self._set_status("下載中...", ACCENT)
        self.log_write(f"開始下載：{url}")
        if browser_selected == "Cookies: 檔案":
            self.log_write(f"使用 Cookies 檔案：{os.path.basename(self.cookies_file_path)}")
        elif browser_selected != "Cookies: 無":
            self.log_write(f"使用瀏覽器餅乾：{browser_selected}")

        def run():
            try:
                import yt_dlp
                final_path = [None]

                def hook(d):
                    if d["status"] == "finished":
                        base = os.path.splitext(d["filename"])[0]
                        final_path[0] = base + ".mp3"

                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
                    "progress_hooks": [hook],
                    "quiet": True,
                    # YouTube (2026)：預設網頁客戶端需要解 JS「n 簽章」挑戰，
                    # 否則會出現 "Requested format is not available"。改用 android_vr
                    # 客戶端可免挑戰、免 cookies 直接取得音訊格式，最穩定。
                    "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
                }
                # 決定要不要帶 cookies（公開影片通常不需要）
                cookie_opt = None
                if browser_selected == "Cookies: 檔案":
                    if self.cookies_file_path and os.path.exists(self.cookies_file_path):
                        cookie_opt = ("cookiefile", self.cookies_file_path)
                else:
                    browser_map = {
                        "Cookies: Chrome": "chrome",
                        "Cookies: Edge": "edge",
                        "Cookies: Firefox": "firefox",
                        "Cookies: Brave": "brave",
                        "Cookies: Opera": "opera",
                        "Cookies: Safari": "safari",
                    }
                    browser_name = browser_map.get(browser_selected)
                    if browser_name:
                        cookie_opt = ("cookiesfrombrowser", (browser_name,))

                def _do_download(opts):
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])

                try:
                    opts = dict(ydl_opts)
                    if cookie_opt:
                        opts[cookie_opt[0]] = cookie_opt[1]
                    _do_download(opts)
                except Exception as e:
                    msg = str(e).lower()
                    # cookies 讀取失敗（如該瀏覽器未安裝 / 找不到設定檔）→ 自動改用無 cookies 重試
                    cookie_failed = cookie_opt and any(
                        k in msg for k in ("cookie", "could not find", "database", "profile")
                    )
                    if cookie_failed:
                        self.root.after(0, lambda: self.log_write(
                            "Cookies 讀取失敗（該瀏覽器可能未安裝），改用無 cookies 重新下載…"))
                        _do_download(dict(ydl_opts))
                    else:
                        raise
                self.root.after(0, lambda: self._yt_done(final_path[0]))
            except ImportError:
                self.root.after(0, lambda: self._yt_error("請先安裝 yt-dlp：pip install yt-dlp"))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self._yt_error(err))

        threading.Thread(target=run, daemon=True).start()

    def _yt_done(self, path):
        self.yt_btn.configure(state="normal")
        if path and os.path.exists(path):
            self.audio_var.set(path)
            self.audio_display_var.set(self._short_name(os.path.basename(path)))
            self.log_write(f"下載完成：{os.path.basename(path)}")
            self._set_status("下載完成，可開始轉錄", GREEN)
        else:
            self.log_write("下載完成，請手動選擇音檔")
            self._set_status("下載完成", ACCENT)

    def _yt_error(self, err):
        self.yt_btn.configure(state="normal")
        self.log_write(f"下載錯誤：{err}")
        self._set_status("下載失敗", RED)

    # ── Callbacks ──────────────────────────────────
    def _on_engine_change(self):
        if self.engine_var.get() == "whisperx":
            self.wx_frame.pack(fill="x", pady=(0, 4), before=self.r_out)
        else:
            self.wx_frame.pack_forget()

    def _sync_model_widget(self, engine):
        """切換引擎時更新模型下拉：雲端引擎顯示對應清單與已存值；
        本地引擎（ollama / lmstudio）的模型即 Key 欄位，故隱藏下拉。"""
        if not hasattr(self, "ai_model_combo"):
            return
        if engine in _ENGINE_MODELS:
            self.ai_model_combo.configure(values=_ENGINE_MODELS[engine])
            cfg_key = _ENGINE_MODEL_KEY[engine]
            self.ai_model_var.set(self.cfg.get(cfg_key, _ENGINE_MODEL_DEFAULT[engine]))
            if not self.ai_model_row.winfo_ismapped():
                self.ai_model_row.pack(fill="x", anchor="w", pady=(6, 0),
                                       before=self.ai_key_row)
        else:
            self.ai_model_row.pack_forget()

    def _on_model_change(self, *_):
        """模型下拉變動（點選或手動輸入）即存進 config 對應欄位。"""
        if not hasattr(self, "ai_model_combo"):
            return
        engine = self.ai_engine_var.get()
        if engine not in _ENGINE_MODEL_KEY:
            return
        model = self.ai_model_var.get().strip()
        if not model:
            return
        cfg_key = _ENGINE_MODEL_KEY[engine]
        if self.cfg.get(cfg_key) == model:  # 沒變就不重複寫檔（含程式設定值時）
            return
        save_config({cfg_key: model})
        self.cfg[cfg_key] = model

    def _on_ai_engine_change(self):
        engine = self.ai_engine_var.get()
        if hasattr(self, "verify_btn"):  # 切換引擎時清掉上次的驗證結果
            self.verify_btn.configure(text="驗證")
        self._sync_model_widget(engine)
        if engine == "claude":
            self.ai_key_label.configure(text="Claude Key")
            self.ai_key_var.set(self.cfg.get("anthropic_key", ""))
            self.ai_key_entry.configure(show="*")
        elif engine == "openai":
            self.ai_key_label.configure(text="OpenAI Key")
            self.ai_key_var.set(self.cfg.get("openai_key", ""))
            self.ai_key_entry.configure(show="*")
        elif engine == "ollama":
            self.ai_key_label.configure(text="Model 名稱")
            self.ai_key_var.set(self.cfg.get("ollama_model", "qwen2.5:7b"))
            self.ai_key_entry.configure(show="")
        elif engine == "lmstudio":
            self.ai_key_label.configure(text="Model 名稱")
            self.ai_key_var.set(self.cfg.get("lmstudio_model", "google/gemma-4-e4b"))
            self.ai_key_entry.configure(show="")
        else:
            self.ai_key_label.configure(text="Gemini Key")
            self.ai_key_var.set(self.cfg.get("gemini_key", ""))
            self.ai_key_entry.configure(show="*")

    def _update_verify_btn(self, *_):
        """依輸入框是否有值切換「驗證」鈕外觀：有值→藍色醒目，空白→暗色。"""
        if not hasattr(self, "verify_btn"):
            return
        if self.ai_key_var.get().strip():
            self.verify_btn.configure(fg_color=ACCENT, hover_color=BLUE, text_color="white")
        else:
            self.verify_btn.configure(fg_color=SURFACE, hover_color=BORDER, text_color=SUBTEXT)

    def _verify_api(self):
        ai_engine = self.ai_engine_var.get()
        api_key = self.ai_key_var.get().strip()
        is_local = ai_engine in ("ollama", "lmstudio")
        if not api_key and not is_local:
            self.log_write(f"請先輸入 {_ENGINE_DISPLAY.get(ai_engine, ai_engine)} API Key")
            return
        self.verify_btn.configure(state="disabled", text="驗證中")
        self._set_status(f"正在驗證 {_ENGINE_DISPLAY.get(ai_engine, ai_engine)}...", ACCENT)

        def run():
            try:
                ok, msg = verify_engine(ai_engine, api_key)
            except Exception as e:
                ok, msg = False, str(e)
            self.root.after(0, lambda: self._verify_done(ai_engine, api_key, is_local, ok, msg))

        threading.Thread(target=run, daemon=True).start()

    def _verify_done(self, ai_engine, api_key, is_local, ok, msg):
        self.verify_btn.configure(state="normal", text="驗證")
        if ok:
            self.verify_btn.configure(fg_color=GREEN_DIM, text_color="white")
            self.log_write(f"✓ {msg}")
            self._set_status(f"✓ {msg}", GREEN)
            if not is_local:  # 驗證通過順手存下金鑰
                cfg_key = _ENGINE_CFG_KEY[ai_engine]
                save_config({cfg_key: api_key})
                self.cfg[cfg_key] = api_key
        else:
            self._update_verify_btn()
            self.log_write(f"✗ 驗證失敗：{msg}")
            self._set_status("驗證失敗", RED)

    def _on_cookies_change(self, choice):
        if choice == "Cookies: 選擇檔案...":
            self.pick_cookies_file()
        elif choice == "Cookies: 檔案":
            if not self.cookies_file_path or not os.path.exists(self.cookies_file_path):
                self.pick_cookies_file()

    def pick_cookies_file(self):
        path = filedialog.askopenfilename(
            title="選擇 Cookies 檔案",
            filetypes=[
                ("文字檔", "*.txt"),
                ("所有檔案", "*.*")
            ],
            parent=self.root
        )
        if path:
            self.cookies_file_path = path
            save_config({"cookies_file_path": path, "cookies_browser": "Cookies: 檔案"})
            self.cfg["cookies_file_path"] = path
            self.cfg["cookies_browser"] = "Cookies: 檔案"
            self.cookies_browser_var.set("Cookies: 檔案")
            self.log_write(f"已載入 Cookies 檔案：{os.path.basename(path)}")
        else:
            if not self.cookies_file_path or not os.path.exists(self.cookies_file_path):
                self.cookies_browser_var.set("Cookies: 無")

    def pick_audio(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("音訊/影片檔", "*.m4a *.mp3 *.wav *.mp4 *.mkv *.avi *.mov *.webm *.ogg *.flac"),
                ("音訊檔", "*.m4a *.mp3 *.wav *.ogg *.flac"),
                ("影片檔", "*.mp4 *.mkv *.avi *.mov *.webm"),
                ("所有檔案", "*.*"),
            ])
        if path:
            self.audio_var.set(path)
            self.audio_display_var.set(self._short_name(os.path.basename(path)))
            ext = os.path.splitext(path)[1].lower()
            self.srt_var.set(ext in VIDEO_EXTS)
            if not self.out_var.get():
                self.out_var.set(os.path.dirname(path))
                self.out_display_var.set(os.path.dirname(path))

    def pick_output(self):
        path = filedialog.askdirectory()
        if path:
            self.out_var.set(path)
            self.out_display_var.set(path)

    def log_write(self, msg):
        self.log.configure(state="normal")
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def update_timer(self):
        if self.timer_start is not None:
            elapsed = int(time.time() - self.timer_start)
            self.timer_var.set(f"{elapsed//3600:02d}:{(elapsed%3600)//60:02d}:{elapsed%60:02d}")
            self.timer_id = self.root.after(1000, self.update_timer)

    def _elapsed_str(self):
        """目前已經過的時間字串（HH:MM:SS）。"""
        if self.timer_start is None:
            return self.timer_var.get()
        el = int(time.time() - self.timer_start)
        return f"{el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}"

    def _stop_timer(self):
        """停止計時並把標籤凍結在最終時間。"""
        final = self._elapsed_str()
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.timer_start = None
        self.timer_var.set(final)
        return final

    # ── AI 進度動畫 ────────────────────────────────
    def _start_ai_progress(self):
        self.timer_start = time.time()
        self.update_timer()
        self.pct_var.set("")
        self._ai_anim_running = True
        self._ai_anim_val = 0.0
        self._ai_anim_dir = 1
        self._animate_ai_progress()

    def _animate_ai_progress(self):
        if not self._ai_anim_running:
            return
        self._ai_anim_val += self._ai_anim_dir * 0.025
        if self._ai_anim_val >= 1.0:
            self._ai_anim_val = 1.0
            self._ai_anim_dir = -1
        elif self._ai_anim_val <= 0.0:
            self._ai_anim_val = 0.0
            self._ai_anim_dir = 1
        self.progress.set(self._ai_anim_val)
        self.root.after(40, self._animate_ai_progress)

    def _stop_ai_progress(self, success=True):
        self._ai_anim_running = False
        self.progress.set(1.0 if success else 0.0)
        self._stop_timer()

    def _set_status(self, msg, color=SUBTEXT):
        self.status_label.configure(text=msg, text_color=color)

    def _short_name(self, name, maxlen=22):
        return name if len(name) <= maxlen else name[:maxlen - 1] + "…"

    # ── Poll & Transcription ───────────────────────
    def poll(self):
        try:
            while True:
                pct = self.prog_q.get_nowait()
                self.progress.set(pct / 100)
                self.pct_var.set(f"{pct}%")
        except Exception:
            pass
        try:
            while True:
                self.log_write(self.log_q.get_nowait())
        except Exception:
            pass
        try:
            status, data = self.result_q.get_nowait()
            # 先停錶並記下總耗時，避免後續任何步驟丟例外導致計時器停不下來
            elapsed = self._stop_timer()
            if status == "done":
                self.progress.set(1.0)
                self.pct_var.set("100%")
                self.log_write(f"完成！耗時 {elapsed}，儲存至：{data}")
                self._set_status(f"轉錄完成（耗時 {elapsed}）！已切到「逐字稿處理」分頁", GREEN)
                speakers = self._find_speakers(data)
                if speakers:
                    dlg = SpeakerNameDialog(self.root, speakers)
                    if dlg.result:
                        self._rename_speakers(data, dlg.result)
                self.transcript_path = data
                self.loaded_file_var.set(f"已載入：{os.path.basename(data)}")
                _open_file(data)
                self.correct_btn.configure(state="normal", fg_color=BLUE, text_color="white")
                self.notes_btn.configure(state="normal", fg_color=BLUE, text_color="white")
                self.export_srt_btn.configure(state="normal", fg_color=BLUE, text_color="white")
                # 轉錄完成自動帶使用者到下一步（AI 後製分頁）
                try:
                    self.tabs.set(self._TAB_AI)
                except Exception:
                    pass
            else:
                self.log_write(f"錯誤：{data}")
                self._set_status(f"發生錯誤（耗時 {elapsed}）", RED)
            self.finish()
            return
        except Exception:
            pass
        if self.process and self.process.is_alive():
            self.root.after(300, self.poll)
        else:
            self.finish()

    def start(self):
        audio = self.audio_var.get().strip()
        out_dir = self.out_var.get().strip()
        if not audio or not os.path.exists(audio):
            self._set_status("請先選擇音檔", RED)
            return
        if not out_dir:
            self._set_status("請選擇輸出資料夾", RED)
            return

        engine = self.engine_var.get()
        lang = LANG_MAP.get(self.lang_var.get())
        prompt = self.prompt_var.get().strip()

        write_srt = self.srt_var.get()
        if write_srt and engine == "whisper":
            switch = messagebox.askyesno(
                "建議切換引擎",
                "輸出字幕時建議使用 WhisperX 引擎，\n可提供逐字對齊、字幕時間戳更精準。\n\n要自動切換到 WhisperX 嗎？\n（選「否」繼續使用 Whisper）",
                parent=self.root,
            )
            if switch:
                self.engine_var.set("whisperx")
                self.wx_frame.grid()
                engine = "whisperx"

        if engine == "whisperx":
            hf_token = self.token_var.get().strip()
            if not hf_token:
                self._set_status("請輸入 HuggingFace Token", RED)
                return
            save_config({"hf_token": hf_token})
            num_speakers = self.speakers_var.get()

        self.correct_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
        self.notes_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
        self.transcript_path = None
        self.result_q = multiprocessing.Queue()
        self.log_q = multiprocessing.Queue()
        self.prog_q = multiprocessing.Queue()

        if engine == "whisperx":
            self.process = multiprocessing.Process(
                target=whisperx_worker,
                args=(audio, out_dir, self.model_var.get(), lang,
                      hf_token, num_speakers, prompt, write_srt,
                      self.result_q, self.log_q, self.prog_q),
                daemon=True)
        else:
            self.process = multiprocessing.Process(
                target=whisper_worker,
                args=(audio, out_dir, self.model_var.get(), lang, prompt, write_srt,
                      self.result_q, self.log_q, self.prog_q),
                daemon=True)

        self.process.start()
        self.progress.set(0)
        self.pct_var.set("0%")
        self.start_btn.configure(state="disabled", fg_color=GREEN_DIM)
        self.stop_btn.configure(state="normal")
        self._set_status("轉錄中，請稍候...", ACCENT)
        self.timer_start = time.time()
        self.update_timer()
        self.poll()

    def stop(self):
        if self.process and self.process.is_alive():
            self.process.terminate()
            self.process.join()
            self.log_write("已手動停止")
            self._set_status("已停止", SUBTEXT)
            self.finish()
        else:
            self.ai_cancelled = True
            self.log_write("正在取消，請稍候...")
            self._set_status("取消中...", SUBTEXT)

    def finish(self):
        self.start_btn.configure(state="normal", fg_color=GREEN)
        self.stop_btn.configure(state="disabled")
        self._stop_timer()
        self.process = None

    # ── Transcript helpers ─────────────────────────
    def load_transcript(self):
        path = filedialog.askopenfilename(
            filetypes=[("逐字稿 / Markdown 文件", "*.txt *.md *.markdown"),
                       ("Markdown 文件", "*.md *.markdown"),
                       ("所有檔案", "*.*")])
        if not path:
            return
        speakers = self._find_speakers(path)
        if speakers:
            dlg = SpeakerNameDialog(self.root, speakers)
            if dlg.result:
                self._rename_speakers(path, dlg.result)
        self.transcript_path = path
        fname = os.path.basename(path)
        self.loaded_file_var.set(f"已載入：{fname}")
        self.correct_btn.configure(state="normal", fg_color=BLUE, text_color="white")
        self.notes_btn.configure(state="normal", fg_color=BLUE, text_color="white")
        self.export_srt_btn.configure(state="normal", fg_color=BLUE, text_color="white")
        self.log_write(f"已載入逐字稿：{fname}")
        self._set_status("已載入，請點選「校正逐字稿」或「產生摘要」", ACCENT)

    def _resolve_output_path(self, path):
        if not os.path.exists(path):
            return path
        overwrite = messagebox.askyesno(
            "檔案已存在",
            f"{os.path.basename(path)} 已存在，是否覆蓋？\n選「否」將自動另外命名。",
            parent=self.root,
        )
        if overwrite:
            return path
        base, ext = os.path.splitext(path)
        n = 2
        while os.path.exists(f"{base}_{n}{ext}"):
            n += 1
        return f"{base}_{n}{ext}"

    def _find_speakers(self, path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return sorted(set(re.findall(r"SPEAKER_\d+", content)))

    def _rename_speakers(self, path, name_map):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for original, new_name in name_map.items():
            if original != new_name:
                content = content.replace(original, new_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ── AI operations ──────────────────────────────
    def correct_transcript(self):
        if not self.transcript_path:
            return
        ai_engine = self.ai_engine_var.get()
        api_key = self.ai_key_var.get().strip()
        if not api_key and ai_engine not in ("ollama", "lmstudio"):
            self.log_write(f"請輸入 {_ENGINE_DISPLAY.get(ai_engine, ai_engine)} API Key")
            return
        base = self.transcript_path.rsplit("_transcript", 1)[0]
        out_path = self._resolve_output_path(base + "_transcript_corrected.txt")
        cfg_key = _ENGINE_CFG_KEY[ai_engine]
        save_config({cfg_key: api_key})
        self.cfg[cfg_key] = api_key

        self.ai_cancelled = False
        self.correct_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
        self.notes_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
        self.stop_btn.configure(state="normal")
        self.log_write(f"正在校正逐字稿（{_ENGINE_DISPLAY.get(ai_engine, ai_engine)}）...")
        self._set_status("校正中...", ACCENT)
        self._start_ai_progress()

        def run():
            try:
                result = correct_transcript(self.transcript_path, ai_engine, api_key, out_path, context=self.prompt_var.get().strip())
                self.root.after(0, lambda: self._correct_done(result))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self._correct_error(err))

        threading.Thread(target=run, daemon=True).start()

    def _correct_done(self, out_path):
        self._stop_ai_progress(success=not self.ai_cancelled)
        self._reset_ai_buttons()
        if self.ai_cancelled:
            self.log_write("校正已取消")
            self._set_status("已取消", SUBTEXT)
            return
        self.transcript_path = out_path
        self.loaded_file_var.set(f"已載入：{os.path.basename(out_path)}")
        self.log_write(f"校正完成：{os.path.basename(out_path)}")
        self._set_status("校正完成！已自動開啟，可繼續點選「產生摘要」", GREEN)
        _open_file(out_path)

    def _correct_error(self, err):
        self._stop_ai_progress(success=False)
        self._reset_ai_buttons()
        self.log_write(f"校正錯誤：{err}")
        self._set_status("校正失敗", RED)

    def generate_notes(self):
        if not self.transcript_path:
            return
        ai_engine = self.ai_engine_var.get()
        api_key = self.ai_key_var.get().strip()
        if not api_key and ai_engine not in ("ollama", "lmstudio"):
            self.log_write(f"請輸入 {_ENGINE_DISPLAY.get(ai_engine, ai_engine)} API Key")
            return
        default_out = self.transcript_path.replace("_transcript.txt", "_摘要.docx")
        if default_out == self.transcript_path:
            default_out = self.transcript_path.rsplit(".", 1)[0] + "_摘要.docx"
        out_path = self._resolve_output_path(default_out)
        cfg_key = _ENGINE_CFG_KEY[ai_engine]
        save_config({cfg_key: api_key})
        self.cfg[cfg_key] = api_key

        self.ai_cancelled = False
        self.correct_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
        self.notes_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
        self.stop_btn.configure(state="normal")
        self.log_write(f"正在產生摘要（{_ENGINE_DISPLAY.get(ai_engine, ai_engine)}）...")
        self._set_status("產生摘要中...", ACCENT)
        self._start_ai_progress()

        def run():
            try:
                result = generate_summary(self.transcript_path, ai_engine, api_key, out_path, context=self.prompt_var.get().strip())
                self.root.after(0, lambda: self._notes_done(result))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self._notes_error(err))

        self.notes_thread = threading.Thread(target=run, daemon=True)
        self.notes_thread.start()

    def export_srt(self):
        if not self.transcript_path:
            return
        base = self.transcript_path.rsplit(".", 1)[0]
        for suffix in ("_transcript_corrected", "_transcript"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        out_path = self._resolve_output_path(base + ".srt")

        ai_engine = self.ai_engine_var.get()
        api_key = self.ai_key_var.get().strip()

        if api_key:
            self.ai_cancelled = False
            self.export_srt_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
            self.correct_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
            self.notes_btn.configure(state="disabled", fg_color=BLUE_DIM, text_color=SUBTEXT)
            self.stop_btn.configure(state="normal")
            self.log_write(f"正在用 AI 切割字幕（{_ENGINE_DISPLAY.get(ai_engine, ai_engine)}）...")
            self._set_status("AI 切割字幕中...", ACCENT)
            self._start_ai_progress()

            srt_source = base + ".srt"
            use_srt = os.path.exists(srt_source)
            if use_srt:
                self.log_write("找到原始 SRT，使用毫秒精準時間戳...")
            else:
                self.log_write("未找到原始 SRT，改用 TXT 時間戳（整數秒）...")

            def run():
                try:
                    if use_srt:
                        segments = _parse_srt(srt_source)
                        entries = _ai_cut_segments(segments, ai_engine, api_key)
                        _write_srt(entries, out_path)
                        result = out_path
                    else:
                        result = txt_to_srt_ai(self.transcript_path, ai_engine, api_key, out_path)
                    self.root.after(0, lambda: self._export_srt_done(result))
                except Exception as e:
                    err = str(e)
                    self.root.after(0, lambda: self._export_srt_error(err))

            threading.Thread(target=run, daemon=True).start()
        else:
            try:
                txt_to_srt(self.transcript_path, out_path)
                self.log_write(f"SRT 已匯出：{os.path.basename(out_path)}")
                self._set_status("SRT 匯出完成！", GREEN)
            except Exception as e:
                self.log_write(f"SRT 匯出錯誤：{e}")
                self._set_status("SRT 匯出失敗", RED)

    def _export_srt_done(self, out_path):
        self._stop_ai_progress(success=not self.ai_cancelled)
        self._reset_ai_buttons()
        if self.ai_cancelled:
            self.log_write("SRT 匯出已取消")
            self._set_status("已取消", SUBTEXT)
            return
        self.log_write(f"SRT 已匯出：{os.path.basename(out_path)}")
        self._set_status("SRT 匯出完成！", GREEN)

    def _export_srt_error(self, err):
        self._stop_ai_progress(success=False)
        self._reset_ai_buttons()
        self.log_write(f"SRT 匯出錯誤：{err}")
        self._set_status("SRT 匯出失敗", RED)

    def _notes_done(self, out_path):
        self._stop_ai_progress(success=not self.ai_cancelled)
        self._reset_ai_buttons()
        if self.ai_cancelled:
            self.log_write("產生摘要已取消")
            self._set_status("已取消", SUBTEXT)
            return
        self.log_write(f"摘要已儲存：{os.path.basename(out_path)}")
        self._set_status("摘要完成！已自動開啟", GREEN)
        _open_file(out_path)

    def _notes_error(self, err):
        self._stop_ai_progress(success=False)
        self._reset_ai_buttons()
        self.log_write(f"摘要錯誤：{err}")
        self._set_status("摘要失敗", RED)

    def _reset_ai_buttons(self):
        self.stop_btn.configure(state="disabled")
        self.correct_btn.configure(state="normal", fg_color=BLUE, text_color="white")
        self.notes_btn.configure(state="normal", fg_color=BLUE, text_color="white")
        self.export_srt_btn.configure(state="normal", fg_color=BLUE, text_color="white")


def _enable_mac_clipboard(root):
    """macOS：tkinter 預設的 Cmd+C / Cmd+V / Cmd+X / Cmd+A 常失效，
    這裡手動把它們綁定到目前聚焦的輸入框。"""
    if sys.platform != "darwin":
        return

    def _fire(event_name):
        def handler(event):
            try:
                event.widget.event_generate(event_name)
            except Exception:
                pass
            return "break"
        return handler

    def _is_masked(w):
        # 遮罩欄位（show="*"）= API key / token，使用者一定整段貼上。
        try:
            return bool(w.cget("show"))
        except Exception:
            return False

    def _paste(event):
        # macOS Tk 的 <<Paste>> 虛擬事件常因焦點時機失靈，
        # 改成直接讀剪貼簿、手動插入（適用 Entry 與 Text），失敗才退回虛擬事件。
        w = event.widget
        try:
            text = w.clipboard_get()
        except Exception:
            return "break"
        # 遮罩欄位（key/token）：整個取代並去除前後空白/換行，
        # 避免看不見的殘值累加成壞字串（這是同事 key 401 的真正根因）。
        if _is_masked(w):
            try:
                w.delete(0, "end")
                w.insert(0, text.strip())
                return "break"
            except Exception:
                pass
        try:
            w.delete("sel.first", "sel.last")   # 有選取就先覆蓋
        except Exception:
            pass
        try:
            w.insert("insert", text)
        except Exception:
            try:
                w.event_generate("<<Paste>>")
            except Exception:
                pass
        return "break"

    def _select_all(event):
        # macOS 的 <<SelectAll>> 虛擬事件不可靠，改用手動全選。
        w = event.widget
        try:
            w.select_range(0, "end")            # Entry / CTkEntry
            w.icursor("end")
        except Exception:
            try:
                w.tag_add("sel", "1.0", "end")  # Text
            except Exception:
                pass
        return "break"

    root.bind_all("<Command-c>", _fire("<<Copy>>"))
    root.bind_all("<Command-v>", _paste)
    root.bind_all("<Command-x>", _fire("<<Cut>>"))
    root.bind_all("<Command-a>", _select_all)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = ctk.CTk()
    app = TranscribeApp(root)
    _enable_mac_clipboard(root)
    root.mainloop()
