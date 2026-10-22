#!/usr/bin/env python3
"""生成した投稿を、アカウント定義に照らして機械判定する。

「プロンプトに禁止事項を書く」だけでは守られない。書いたあとに測る。
FAIL が1つでもあれば終了コード1を返すので、生成→チェック→再生成が自動で回せる。

使い方:
    python3 engine/check_post.py accounts/yu.json draft.md --md
    python3 engine/check_post.py accounts/yu.json posts/x.md --md --section 悠
"""
import argparse
import difflib
import json
import re
import sys

from extract_voice import (URL, EMOJI, FIRST_PERSON, as_text, blocks_from_md, blocks_from_plain,
                           reader_questions, sentences, slide_of, tail)

CTA_MARKERS = ["プロフ", "固定", "過去の投稿", "過去投稿", "note", "リンク", "https://", "ハイライト"]
# 処方＝今夜そのまま実行できる動作。これが無い投稿は「慰めただけ」で保存もされない
MOVE_VERBS = ["やめる", "やめて", "変える", "変えて", "抜く", "足さない", "出す", "送る", "聞く",
              "置く", "流す", "止める", "選ばせる", "決めさせる", "待たない", "合わせにいかない"]
# 免罪。1行までは救済として要るが、重ねると主張が免罪に寄ってターゲットから外れる
ABSOLUTION = ["せいじゃない", "悪くない", "下手だったわけじゃない", "仕方なかった",
              "構造の話", "価値の話じゃない", "教わってないだけ", "重かったわけじゃない"]
GREEN, RED, YEL, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def ngrams(text, n=5):
    t = re.sub(r"\s+", "", URL.sub("", text))
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def similarity(draft, ref):
    """下書きと参考投稿の近さ。最長一致と5-gram重複率で見る。

    型（構成・文字数配分・フックの作り方）を借りるのは問題ないが、
    文そのものが残っていると丸パクリになる。文字列として測れば機械で止められる。
    """
    a = re.sub(r"\s+", "", URL.sub("", draft))
    b = re.sub(r"\s+", "", URL.sub("", ref))
    if not a or not b:
        return {"lcs": 0, "lcs_text": "", "overlap": 0.0}
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    ga, gb = ngrams(a), ngrams(b)
    return {
        "lcs": m.size,
        "lcs_text": a[m.a:m.a + m.size],
        "overlap": round(len(ga & gb) / max(1, len(ga)), 3),
    }


def check_similarity(blocks, ref_path, rep):
    from analyze_buzz import posts_from_md, posts_from_plain

    text = open(ref_path, encoding="utf-8").read()
    refs = posts_from_md(text) or posts_from_plain(text)
    if not refs:
        rep.add("WARN", "[類似度]", f"{ref_path} から参考投稿を読めなかった")
        return

    draft = "".join(as_text(b) for b in blocks)
    worst, worst_ref = {"lcs": 0, "lcs_text": "", "overlap": 0.0}, ""
    for r in refs:
        sim = similarity(draft, "".join(r["slides"]))
        if (sim["lcs"], sim["overlap"]) > (worst["lcs"], worst["overlap"]):
            worst, worst_ref = sim, r["title"]

    pct = round(worst["overlap"] * 100)
    detail = f"最長一致{worst['lcs']}字・重複{pct}%（対 {worst_ref}）"
    if worst["lcs"] >= 25 or worst["overlap"] >= 0.35:
        rep.add("FAIL", "[類似度]", f"参考投稿に寄りすぎ。{detail}「{worst['lcs_text'][:30]}」")
    elif worst["lcs"] >= 15 or worst["overlap"] >= 0.20:
        rep.add("WARN", "[類似度]", f"{detail}「{worst['lcs_text'][:30]}」")
    else:
        rep.add("OK", "[類似度]", detail)


class Report:
    def __init__(self):
        self.rows = []

    def add(self, level, where, msg):
        self.rows.append((level, where, msg))

    def fails(self):
        return [r for r in self.rows if r[0] == "FAIL"]

    def print(self, color=True):
        c = {"FAIL": RED, "WARN": YEL, "OK": GREEN} if color else {"FAIL": "", "WARN": "", "OK": ""}
        o = OFF if color else ""
        for level, where, msg in self.rows:
            print(f"  {c[level]}{level:<4}{o} {where:<12} {msg}")


def check_thread(i, blk, acc, rep):
    ng = acc.get("ng", {})
    meas = acc["voice"]["measured"]
    block = as_text(blk)
    slide = slide_of(blk, i)
    where = f"[{slide}枚目]"
    body = block.replace("\n", "")
    lines = [l.strip() for l in block.split("\n") if l.strip()]
    # URL の中身は語として数えない（note.com/... の note を禁止ワードにしない）
    prose = URL.sub("", block)

    for w in ng.get("words", []):
        if w in prose:
            rep.add("FAIL", where, f"禁止ワード「{w}」")
    for pat in ng.get("expressions", []):
        m = re.search(pat, prose)
        if m:
            rep.add("FAIL", where, f"禁止表現「{m.group(0)}」（/{pat}/）")

    if ng.get("no_questions"):
        for q in reader_questions(block):
            rep.add("FAIL", where, f"読者への問いかけ「{q}」")

    if ng.get("no_emoji") and EMOJI.search(block):
        rep.add("FAIL", where, f"絵文字 {''.join(EMOJI.findall(block))}")

    # 文字数は1枚目・2枚目…で狙いが違うので、スライド位置別の実測レンジで見る
    by = meas["length"].get("chars_by_slide", {}).get(str(slide))
    rng = by or meas["length"]["chars_per_thread"]
    lo, hi = rng["p25"], rng["p75"]
    src = f"{slide}枚目の実測" if by else "実測"
    n = len(body)
    if not (lo * 0.75 <= n <= hi * 1.25):
        level = "FAIL" if not (lo * 0.5 <= n <= hi * 1.5) else "WARN"
        rep.add(level, where, f"文字数 {n}字（{src}レンジ {lo}〜{hi}字）")

    cap = meas["length"]["chars_per_line_p90"]
    long_lines = [l for l in lines if len(l) > cap * 1.3]
    if long_lines:
        rep.add("WARN", where, f"1行が長い {len(long_lines)}行（実測上限 {cap}字）: 「{long_lines[0][:24]}…」")

    allowed = {acc["identity"]["first_person"]} | set(meas["person"]["first"])
    for w in FIRST_PERSON:
        if w not in allowed and w in block:
            rep.add("WARN", where, f"定義外の一人称「{w}」")

    sp = acc["identity"].get("second_person")
    if sp is None:
        for w in ["あなた", "きみ", "君"]:
            if w in block:
                rep.add("WARN", where, f"二人称「{w}」（この人は主語なしで書く）")


def check_prescription(blocks, acc, rep):
    """主張が免罪で終わっていないかを測る。

    理由の説明と免罪だけで終わった投稿は、読者から見ると慰められただけで何も渡されていない。
    締めの2スレッドに「今夜そのまま実行できる動作」が入っているかを必須にする。
    """
    pre = acc.get("prescription")
    if not pre:
        rep.add("WARN", "[処方]", "アカウント定義に prescription が無い。投稿が免罪で終わりやすい")
        return

    closing = "\n".join(as_text(b) for b in blocks[-2:])
    lines = [l.strip() for l in closing.split("\n") if l.strip()]

    marks = [k for k in pre.get("move_markers", []) if k in closing]
    verbs = [v for v in MOVE_VERBS if v in closing]
    if marks and verbs:
        rep.add("OK", "[処方]", f"今夜やる1手あり（{marks[:2]} / {verbs[:2]}）")
    else:
        miss = "動作の語がない" if not verbs else "今夜やる形になっていない"
        rep.add("FAIL", "[処方]", f"処方が見つからない（{miss}）。例: {pre.get('moves', ['—'])[0]}")

    hit = [l for l in lines if any(w in l for w in ABSOLUTION)]
    cap = pre.get("absolution_lines_max", 1)
    if len(hit) > cap:
        rep.add("WARN", "[処方]", f"免罪が{len(hit)}行で上限{cap}行を超えている（例「{hit[0][:18]}」）")


def check_post(blocks, acc, rep):
    meas = acc["voice"]["measured"]
    first, last = blocks[0], blocks[-1]

    kws = acc.get("themes", {}).get("hook_keywords", [])
    if kws:
        hit = [k for k in kws if k in as_text(first)]
        if hit:
            rep.add("OK", "[フック]", f"ジャンルキーワード {hit}")
        else:
            rep.add("FAIL", "[フック]", f"1枚目にジャンルキーワードなし（候補 {kws[:5]}…）")

    hook = [l.strip() for l in as_text(first).split("\n") if l.strip()][0]
    h = meas["length"]["hook_chars"]
    if not (h["p25"] * 0.7 <= len(hook) <= h["p75"] * 1.4):
        rep.add("WARN", "[フック]", f"1行目 {len(hook)}字（実測 {h['p25']}〜{h['p75']}字）")

    last = as_text(last)
    if not any(m in last for m in CTA_MARKERS):
        rep.add("FAIL", "[締め]", "CTAが見つからない（" + " / ".join(acc["funnel"]["cta_types"]) + "）")
    if any("でもね" in r for r in acc["funnel"].get("rules", [])) and "でもね" not in last:
        rep.add("WARN", "[締め]", "CTA直前の救済一行「でもね」がない")

    check_prescription(blocks, acc, rep)

    tops = {e["tail"] for e in meas["endings_top10"]}
    ss = [s for b in blocks for s in sentences(as_text(b))]
    hits = sum(1 for s in ss if tail(s) in tops)
    score = round(hits / max(1, len(ss)) * 100)
    level = "OK" if score >= 15 else ("WARN" if score >= 8 else "FAIL")
    rep.add(level, "[口調]", f"語尾一致 {score}%（{hits}/{len(ss)}文が実測top10の語尾）")


def run_batch(text, acc, a):
    """### 見出し単位で1投稿とみなして全部チェックする。1日分の出力をまとめて検品する用。"""
    if a.section:
        parts = re.split(r"^## ", text, flags=re.M)
        text = "\n".join(p for p in parts if p.startswith(a.section))
    posts = [("### " + s) for s in re.split(r"^### ", text, flags=re.M)[1:]]
    if not posts:
        sys.exit("### 見出しが見つからない")

    total_fail = 0
    color = sys.stdout.isatty()
    print(f"\n{acc['identity']['name']}（{acc['handle']}）／{len(posts)}本を検品\n")
    for src in posts:
        title = src.split("\n")[0][4:]
        blocks = blocks_from_md(src)
        if not blocks:
            continue
        rep = Report()
        for i, b in enumerate(blocks, 1):
            check_thread(i, b, acc, rep)
        check_post(blocks, acc, rep)
        if a.against:
            check_similarity(blocks, a.against, rep)
        f = len(rep.fails())
        total_fail += f
        mark = (RED + "FAIL" + OFF) if color and f else (GREEN + "pass" + OFF if color else ("FAIL" if f else "pass"))
        print(f"  {mark}  {title[:44]}")
        if f:
            for level, where, msg in rep.rows:
                if level == "FAIL":
                    print(f"          {where} {msg}")
    print(f"\n  合計 FAIL {total_fail}件 / {len(posts)}本\n")
    return 1 if total_fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("account")
    ap.add_argument("post")
    ap.add_argument("--md", action="store_true", help="コードブロックを本文として読む")
    ap.add_argument("--section")
    ap.add_argument("--json", action="store_true", help="機械可読で出す")
    ap.add_argument("--batch", action="store_true",
                    help="### 見出しごとに別の投稿として一括チェックする")
    ap.add_argument("--against", help="参考投稿ファイル。丸パクリになっていないか類似度で見る")
    a = ap.parse_args()

    acc = json.load(open(a.account, encoding="utf-8"))
    if not acc.get("voice", {}).get("measured"):
        sys.exit("voice.measured が空。先に engine/update_voice.py を回すこと")

    text = open(a.post, encoding="utf-8").read()

    if a.batch:
        return run_batch(text, acc, a)

    blocks = blocks_from_md(text, a.section) if a.md else blocks_from_plain(text)
    if not blocks:
        sys.exit("投稿が取れなかった（--md を付け忘れてないか）")

    rep = Report()
    for i, b in enumerate(blocks, 1):
        check_thread(i, b, acc, rep)
    check_post(blocks, acc, rep)
    if a.against:
        check_similarity(blocks, a.against, rep)

    if a.json:
        print(json.dumps(
            {"account": acc["handle"], "threads": len(blocks),
             "rows": [{"level": l, "where": w, "message": m} for l, w, m in rep.rows],
             "pass": not rep.fails()},
            ensure_ascii=False, indent=2))
    else:
        print(f"\n{acc['identity']['name']}（{acc['handle']}）／{len(blocks)}スレッド")
        rep.print(color=sys.stdout.isatty())
        f = len(rep.fails())
        print(f"\n  {'❌ FAIL ' + str(f) + '件。書き直すこと' if f else '✅ PASS'}\n")
    return 1 if rep.fails() else 0


if __name__ == "__main__":
    sys.exit(main())
