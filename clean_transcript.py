"""
自動清理 Whisper/WhisperX 幻覺重複片段
用法：python clean_transcript.py <input_file>
輸出：<input_file>_cleaned.txt
"""
import re
import sys
import os


def collapse(text):
    # 逗號/頓號分隔的重複：對,對,對,對 / 可以了,可以了,可以了
    text = re.sub(
        r'([一-鿿！？。]{1,8})([,，、]\1){2,}',
        r'\1',
        text,
    )
    # 無分隔符短字重複：對對對對 / 電腦電腦電腦 / 偏偏偏偏
    text = re.sub(
        r'([一-鿿]{1,4})\1{3,}',
        r'\1',
        text,
    )
    # 空白分隔短句重複：我懂了 我懂了 我懂了 / 然後呢 然後呢
    text = re.sub(
        r'([一-鿿，。？！、]{2,10})( \1){2,}',
        r'\1',
        text,
    )
    # 完整句子重複（以問號或逗號結尾的長句）
    text = re.sub(
        r'([一-鿿，。？！、 ]{8,30}[？。，！])\s*(\1\s*){1,}',
        r'\1',
        text,
    )
    return text


def clean_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    cleaned = []
    for line in lines:
        stripped = line.rstrip('\n')
        # 只處理有時間戳的內容行
        m = re.match(r'^(\[\d{2}:\d{2} --> \d{2}:\d{2}\] )(.*)', stripped)
        if m:
            ts, content = m.group(1), m.group(2)
            original_len = len(content)
            content = collapse(content)
            # 縮短超過 40% 就加標記，提醒人工確認
            if len(content) < original_len * 0.6:
                content += '　〔⚠ 已壓縮重複〕'
            cleaned.append(ts + content + '\n')
        else:
            cleaned.append(line)

    base, ext = os.path.splitext(path)
    out_path = base + '_cleaned' + ext
    with open(out_path, 'w', encoding='utf-8') as f:
        f.writelines(cleaned)

    print(f'完成：{out_path}')
    return out_path


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法：python clean_transcript.py <transcript.txt>')
        sys.exit(1)
    clean_file(sys.argv[1])
