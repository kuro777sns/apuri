#!/usr/bin/env python3
"""実投稿から口調プロファイル（voice）を実測して JSON で吐く。

形容詞（「フランク」「優しい」）ではなく、数値と分布で口調を定義するための道具。
外部ライブラリなしで動く。

使い方:
    # Markdown の ```コードブロック``` を投稿本文とみなして抽出
    python3 engine/extract_voice.py posts/xxx.md --md --section "悠" --name 悠 --handle @yu.0320.love

    # 空行2つ区切りのプレーンテキストから抽出
    python3 engine/extract_voice.py sample.txt --name テスト
"""
import argparse
import json
import re
import sys
from collections import Counter

SENT_END = "。！？!?"
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️❤]"
)
FIRST_PERSON = ["俺", "僕", "私", "あたし", "自分", "うち"]
SECOND_PERSON = ["あなた", "きみ", "君", "あんた"]
THIRD_PERSON = ["彼", "彼女", "元カレ", "元彼", "旦那", "夫"]
URL = re.compile(r"https?://\S+|[\w.\-]+\.(?:com|jp|net|co|me)/\S*")
# 読者への問いかけ。行末の？を主判定にし、？なしの反語を補助パターンで拾う。
ASK = re.compile(r"(じゃない|ないかな|どう思う|と思わない|してみて欲しい|気づいてる)")


def reader_questions(block):
    """読者への問いかけを列挙する。「」内の会話とURLは数えない。"""
    text = URL.sub("", block)
    text = re.sub(r"「[^」]*」", "", text)
    hits = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.endswith(("？", "?")):
            hits.append(line[-20:])
        elif line.endswith(("でしょうか。", "でしょうか", "ませんか。", "ませんか")):
            hits.append(line[-20:])
        elif ASK.search(line) and line.endswith(("かな", "かな。")):
            hits.append(line[-20:])
    return hits


def blocks_from_md(text, section=None):
    """Markdown からコードブロックを取り出す。section 指定時は ## 見出しで絞る。

    直前の `**Nスレッド目 / 全M**` ラベルからスライド番号を拾う。
    1枚目と3枚目では狙う文字数が違うので、位置は捨てずに持ち回る。
    """
    if section:
        parts = re.split(r"^## ", text, flags=re.M)
        text = "\n".join(p for p in parts if p.startswith(section))
        if not text:
            return []  # そのファイルに当該アカウントの節がないだけ。複数ファイルを渡せるようにする

    out, prev = [], 0
    for m in re.finditer(r"(?:\*\*([^*\n]+)\*\*\s*)?```[a-z]*\n(.*?)```", text, re.S):
        label = (m.group(1) or "").strip()
        num = re.match(r"(\d+)スレッド目", label)
        if num:
            slide = int(num.group(1))
        elif "単発" in label:
            slide = 1
        elif "追記" in label:
            slide = 2
        else:
            slide = prev + 1
        prev = slide
        out.append({"text": m.group(2).strip(), "slide": slide})
    return out


def blocks_from_plain(text):
    """空行2つ区切り。上から順に1枚目・2枚目…とみなす。"""
    return [{"text": b.strip(), "slide": i + 1}
            for i, b in enumerate(re.split(r"\n\s*\n\s*\n", text)) if b.strip()]


def as_text(b):
    return b["text"] if isinstance(b, dict) else b


def slide_of(b, default=1):
    return b.get("slide", default) if isinstance(b, dict) else default


def sentences(block):
    out = []
    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 文末記号で切る。記号がない行はその行を1文とみなす（体言止め対策）
        buf = ""
        for ch in line:
            buf += ch
            if ch in SENT_END:
                out.append(buf.strip())
                buf = ""
        if buf.strip():
            out.append(buf.strip())
    return out


def tail(sent, n=3):
    """語尾。文末記号を落として末尾 n 文字。"""
    s = sent.rstrip(SENT_END).rstrip("」』)）")
    return s[-n:] if len(s) >= n else s


def pct(values, p):
    if not values:
        return 0
    vs = sorted(values)
    k = max(0, min(len(vs) - 1, round((len(vs) - 1) * p / 100)))
    return vs[k]


def analyze(blocks, name, handle):
    block_lens, line_lens, sent_lens, lines_per_block = [], [], [], []
    hook_lens, blank_ratios = [], []
    by_slide = {}
    tails, fp, sp, tp = Counter(), Counter(), Counter(), Counter()
    commas = emojis = asks = sym = 0
    total_sents = 0

    for blk in blocks:
        b, slide = as_text(blk), slide_of(blk)
        raw_lines = b.split("\n")
        content = [l.strip() for l in raw_lines if l.strip()]
        if not content:
            continue
        block_lens.append(len(b.replace("\n", "")))
        by_slide.setdefault(slide, []).append(len(b.replace("\n", "")))
        lines_per_block.append(len(content))
        blank_ratios.append(sum(1 for l in raw_lines if not l.strip()) / max(1, len(raw_lines)))
        hook_lens.append(len(content[0]))
        for l in content:
            line_lens.append(len(l))
        ss = sentences(b)
        total_sents += len(ss)
        for s in ss:
            sent_lens.append(len(s))
            tails[tail(s)] += 1
        commas += b.count("、")
        emojis += len(EMOJI.findall(b))
        asks += len(reader_questions(b))
        sym += sum(b.count(c) for c in "■●▼◆★→")
        for w in FIRST_PERSON:
            fp[w] += b.count(w)
        for w in SECOND_PERSON:
            sp[w] += b.count(w)
        for w in THIRD_PERSON:
            tp[w] += b.count(w)

    n = max(1, len(block_lens))
    return {
        "name": name,
        "handle": handle,
        "measured_from": {"blocks": len(block_lens), "sentences": total_sents},
        "length": {
            "chars_per_thread": {
                "p25": pct(block_lens, 25),
                "median": pct(block_lens, 50),
                "p75": pct(block_lens, 75),
            },
            "chars_by_slide": {
                str(k): {"p25": pct(v, 25), "median": pct(v, 50), "p75": pct(v, 75), "n": len(v)}
                for k, v in sorted(by_slide.items())
            },
            "chars_per_sentence_median": pct(sent_lens, 50),
            "chars_per_line_median": pct(line_lens, 50),
            "chars_per_line_p90": pct(line_lens, 90),
            "hook_chars": {"p25": pct(hook_lens, 25), "median": pct(hook_lens, 50), "p75": pct(hook_lens, 75)},
        },
        "layout": {
            "lines_per_thread_median": pct(lines_per_block, 50),
            "blank_line_ratio": round(sum(blank_ratios) / n, 2),
            "sentences_per_line": round(total_sents / max(1, len(line_lens)), 2),
        },
        "endings_top10": [{"tail": t, "count": c} for t, c in tails.most_common(10)],
        "person": {
            "first": [w for w, c in fp.most_common(3) if c],
            "second": [w for w, c in sp.most_common(3) if c],
            "third": [w for w, c in tp.most_common(3) if c],
            "first_per_thread": round(sum(fp.values()) / n, 2),
            "second_per_thread": round(sum(sp.values()) / n, 2),
        },
        "surface": {
            "commas_per_sentence": round(commas / max(1, total_sents), 2),
            "emoji_per_thread": round(emojis / n, 2),
            "use_emoji": emojis > 0,
            "symbols_per_thread": round(sym / n, 2),
            "questions_to_reader_per_thread": round(asks / n, 2),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--md", action="store_true", help="Markdown のコードブロックを本文として読む")
    ap.add_argument("--section", help="## 見出しで絞り込む")
    ap.add_argument("--name", default="")
    ap.add_argument("--handle", default="")
    ap.add_argument("-o", "--out", help="書き出し先 JSON")
    a = ap.parse_args()

    blocks = []
    for f in a.files:
        text = open(f, encoding="utf-8").read()
        blocks += blocks_from_md(text, a.section) if a.md else blocks_from_plain(text)
    if not blocks:
        sys.exit("投稿が1本も取れなかった")

    prof = analyze(blocks, a.name, a.handle)
    out = json.dumps(prof, ensure_ascii=False, indent=2)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out + "\n")
        print(f"{a.out} に書き出した（{prof['measured_from']['blocks']}本から抽出）")
    else:
        print(out)


if __name__ == "__main__":
    main()
