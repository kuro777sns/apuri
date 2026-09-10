#!/usr/bin/env python3
"""参考にしたいバズ投稿を分解して、なぜ伸びたのかを数字で出し、再利用できる「型カード」にする。

出すのは構造だけ。題材・具体例・固有名詞は型カードに載せない。
借りるのはフックの作り方・文字数配分・構成の運びであって、中身ではない。

投稿ファイルの書き方（どちらでもよい）:

    ### 参考1  imp=120000 like=450 save=30
    ```
    1枚目の本文
    ```
    ```
    2枚目の本文
    ```

    ---
    imp=8000 like=90
    プレーンテキストの投稿。空行2つでスライドを区切る。

数字（imp/like/save/follow/comment）は任意。入れるとリーチ枠といいね枠の判定ができる。

使い方:
    python3 engine/analyze_buzz.py refs.md --md
    python3 engine/analyze_buzz.py refs.md --md --card formats/cards/yabu_A.json
"""
import argparse
import json
import re
import sys
from collections import Counter

from extract_voice import EMOJI, URL, reader_questions, sentences, tail

# ---------------------------------------------------------------- フックの型
# 1行目だけを見て判定する。複数当たったら当たった順に全部返す（型は混ざる）。
HOOK_TYPES = [
    ("数字リスト", r"[0-9０-９]+\s*(個|つ|コ|パターン|段階|ステップ|条件|特徴|サイン|理由|位)|(トップ|ベスト)\s*[0-9０-９]"),
    ("逆張り否定", r"(は逆|じゃない|ではない|は嘘|は間違|違います|勘違い|半分しか|とも外れ|は別物|なんかじゃない)"),
    ("暴露", r"(言わない|教えてくれない|バレる|バレて|隠して|本音|裏側|実は|こっそり|誰も|無意識|つい出|気づかず)"),
    ("自白", r"^(俺|僕|私|自分|あたし).{0,14}(た|てた|かった|んだ|ました)"),
    ("引用", r"^[「『]"),
    ("対比", r"(の違い|は違う|が違う|で違う|の差|の分かれ|で分かれ|は別物|は別|正反対|真逆|とでは)"),
    ("看板", r"^[【\[].{2,24}[】\]]"),
    ("場面指定", r"(人へ|人だけ|方へ|されてる|されて|なってる|止まってる|続いてる|悩んでる)"),
    ("時間期限", r"[0-9０-９]+\s*(秒|分|日|週間|ヶ月|か月|年)"),
    ("損失回避", r"(やめた方|やめとけ|NG|逆効果|損して|後悔|失敗|手遅れ|取り返し)"),
    ("断言", r"(絶対|必ず|全員|100%|間違いなく|断言)"),
]

# ---------------------------------------------------------------- 構成のシグナル
SIGNALS = [
    ("箇条書き", r"^[■●▼◆・\-–—>＞]|^[0-9０-９]+[\.．、)）]"),
    ("セリフ引用", r"[「『][^」』]{2,}[」』]"),
    ("数字", r"[0-9０-９]+"),
    ("未完切り", r"(が、|けど、|のは、|って、|、$|は、$)"),
    ("転換", r"(でもね|でも、|ただ、|だけど|とはいえ|ここから)"),
    ("読者名指し", r"(あなた|きみ|君|〜な人|してる人|してた人)"),
]
CTA_MARKERS = ["プロフ", "固定", "過去の投稿", "過去投稿", "note", "リンク", "https://", "ハイライト", "coconala", "line.me"]

STOP = set("こと それ これ あれ ため よう そう どう する した して いる ある なる れる られ ます です でし ました ません から けど のに ので だけ まで より ほど とか なんか ちゃん さん".split())


def posts_from_md(text):
    """### 見出しごとに1投稿。見出し行にある key=数値 を指標として拾う。"""
    out = []
    for chunk in re.split(r"^### ", text, flags=re.M)[1:]:
        head = chunk.split("\n", 1)[0]
        slides = [m.group(1).strip() for m in re.finditer(r"```[a-z]*\n(.*?)```", chunk, re.S)]
        if slides:
            out.append({"title": re.sub(r"\s*\w+=[\d,]+", "", head).strip(),
                        "metrics": parse_metrics(chunk.split("```")[0]),
                        "slides": slides})
    if out:
        return out
    # 見出しがないなら、コードブロック群をまとめて1投稿とみなす
    slides = [m.group(1).strip() for m in re.finditer(r"```[a-z]*\n(.*?)```", text, re.S)]
    return [{"title": "参考1", "metrics": parse_metrics(text.split("```")[0]), "slides": slides}] if slides else []


def posts_from_plain(text):
    """--- で投稿を区切る。投稿の中は空行2つでスライドを区切る。"""
    out = []
    for i, chunk in enumerate(re.split(r"^\s*-{3,}\s*$", text, flags=re.M), 1):
        body = re.sub(r"^\s*\w+=[\d,]+.*$", "", chunk, flags=re.M)
        slides = [s.strip() for s in re.split(r"\n\s*\n\s*\n", body) if s.strip()]
        if slides:
            out.append({"title": f"参考{i}", "metrics": parse_metrics(chunk), "slides": slides})
    return out


def parse_metrics(head):
    keys = {"imp": "imp", "impressions": "imp", "インプ": "imp", "view": "imp", "views": "imp",
            "like": "like", "いいね": "like", "fav": "like",
            "save": "save", "保存": "save", "follow": "follow", "フォロー": "follow",
            "comment": "comment", "コメント": "comment", "repost": "repost"}
    m = {}
    for k, v in re.findall(r"([A-Za-zぁ-んァ-ヶ一-龥]+)\s*[=:：]\s*([\d,]+)", head or ""):
        if k.lower() in keys:
            m[keys[k.lower()]] = int(v.replace(",", ""))
    return m


def hook_types(hook):
    hits = [name for name, pat in HOOK_TYPES if re.search(pat, hook)]
    return hits or ["分類なし"]


def signals_of(text):
    hits = []
    for name, pat in SIGNALS:
        if re.search(pat, text, re.M):
            hits.append(name)
    return hits


def keywords(posts, top=15):
    """ジャンル語を拾う。形態素解析は使わず、漢字の連なりとカタカナ語を名詞の近似として取る。

    助詞や活用語尾を拾わないよう、切り出しは文字種の切れ目に限る。
    """
    docs = ["".join(p["slides"]) for p in posts]
    df, tf = Counter(), Counter()
    for d in docs:
        d = URL.sub("", d)
        seen = set()
        for m in re.finditer(r"[一-龥]{1,6}|[ァ-ヶー]{2,8}|[A-Za-z]{3,12}", d):
            g = m.group(0)
            if g in STOP:
                continue
            # 単漢字は動詞・形容詞の語幹を拾いやすい。後ろが助詞のときだけ名詞とみなす
            if len(g) == 1:
                nxt = d[m.end():m.end() + 1]
                if nxt and nxt not in "はがをにのもとでや、。」』":
                    continue
                if g in "人事物時的方年月日回度":
                    continue
            tf[g] += 1
            seen.add(g)
        for g in seen:
            df[g] += 1

    cand = [(g, df[g], tf[g]) for g in df if df[g] >= max(2, len(docs) // 2)]
    cand.sort(key=lambda x: (-x[1], -x[2], -len(x[0])))
    return [{"word": g, "posts": d, "count": t} for g, d, t in cand[:top]]


def prose_sentences(ss):
    """語尾を数える対象。箇条書き・セリフだけの行・看板行は地の文ではないので外す。"""
    return [s for s in ss
            if len(s) >= 8 and not re.match(r"^[「『【\[■●▼◆・\-–—>＞0-9０-９]", s)]


def analyze_post(p):
    slides = p["slides"]
    joined = "".join(slides)
    lines = [l.strip() for l in slides[0].split("\n") if l.strip()]
    hook = lines[0] if lines else ""
    ss = [s for sl in slides for s in sentences(sl)]
    m = p["metrics"]

    r = {
        "title": p["title"],
        "slides": len(slides),
        "hook": hook,
        "hook_chars": len(hook),
        "hook_types": hook_types(hook),
        "chars_by_slide": [len(s.replace("\n", "")) for s in slides],
        "chars_total": len(joined.replace("\n", "")),
        "sentence_chars_median": sorted(len(s) for s in ss)[len(ss) // 2] if ss else 0,
        "lines_total": sum(1 for s in slides for l in s.split("\n") if l.strip()),
        "signals": signals_of(joined),
        "endings_top5": [t for t, _ in Counter(tail(s) for s in prose_sentences(ss)).most_common(5)],
        "questions_to_reader": sum(len(reader_questions(s)) for s in slides),
        "emoji": len(EMOJI.findall(joined)),
        "has_cta": any(c in slides[-1] for c in CTA_MARKERS),
    }
    if m:
        r["metrics"] = m
        if m.get("imp"):
            for k in ("like", "save", "follow", "comment"):
                if m.get(k):
                    r[f"{k}_rate"] = round(m[k] / m["imp"] * 100, 3)
            r["slot"] = "like" if r.get("like_rate", 0) >= 0.2 else "reach"
    return r


def cross(rows):
    """全体に共通していることを出す。これが「借りていい部分」。"""
    n = len(rows)
    ht = Counter(t for r in rows for t in r["hook_types"])
    sg = Counter(s for r in rows for s in r["signals"])
    hooks = sorted(r["hook_chars"] for r in rows)
    tot = sorted(r["chars_total"] for r in rows)
    per_slide = {}
    for r in rows:
        for i, c in enumerate(r["chars_by_slide"], 1):
            per_slide.setdefault(i, []).append(c)
    return {
        "posts": n,
        "hook_types": [{"type": t, "posts": c, "率": f"{round(c / n * 100)}%"} for t, c in ht.most_common()],
        "signals": [{"signal": s, "posts": c, "率": f"{round(c / n * 100)}%"} for s, c in sg.most_common()],
        "hook_chars": {"min": hooks[0], "median": hooks[n // 2], "max": hooks[-1]},
        "chars_total": {"min": tot[0], "median": tot[n // 2], "max": tot[-1]},
        "chars_by_slide": {str(k): {"median": sorted(v)[len(v) // 2], "n": len(v)}
                           for k, v in sorted(per_slide.items())},
        "slides": Counter(r["slides"] for r in rows).most_common(),
        "cta率": f"{round(sum(1 for r in rows if r['has_cta']) / n * 100)}%",
        "問いかけ": f"{round(sum(1 for r in rows if r['questions_to_reader']) / n * 100)}%",
        "絵文字": f"{round(sum(1 for r in rows if r['emoji']) / n * 100)}%",
    }


def make_card(rows, cx, kws, name):
    """再利用する型カード。題材は入れない。数字と骨格だけ。"""
    top = cx["hook_types"][0]["type"] if cx["hook_types"] else "分類なし"
    return {
        "name": name,
        "_これは何": "参考投稿から抜いた骨格だけの型。中身は自分のジャンルで一から書く。本文は入っていない",
        "参考にした本数": cx["posts"],
        "hook": {
            "主な型": top,
            "型の分布": cx["hook_types"],
            "文字数": cx["hook_chars"],
        },
        "構成": {
            "スライド数": cx["slides"][0][0] if cx["slides"] else 1,
            "スライド別文字数": cx["chars_by_slide"],
            "合計文字数": cx["chars_total"],
            "使われている仕掛け": cx["signals"],
        },
        "作法": {"CTA": cx["cta率"], "読者への問いかけ": cx["問いかけ"], "絵文字": cx["絵文字"]},
        "_キーワードの扱い": "下は参考アカのジャンル語。そのまま使わず、自分のジャンルの同じ役割の語に置き換える",
        "参考アカのジャンル語": [k["word"] for k in kws],
        "_置き換え表": {k["word"]: "" for k in kws[:8]},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--md", action="store_true", help="コードブロックを本文として読む")
    ap.add_argument("--card", help="型カードJSONの書き出し先")
    ap.add_argument("--name", default="参考型", help="型カードの名前")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    posts = []
    for f in a.files:
        t = open(f, encoding="utf-8").read()
        posts += posts_from_md(t) if a.md else posts_from_plain(t)
    if not posts:
        sys.exit("投稿が取れなかった（--md を付け忘れてないか）")

    rows = [analyze_post(p) for p in posts]
    cx = cross(rows)
    kws = keywords(posts)

    if a.json:
        print(json.dumps({"posts": rows, "共通点": cx, "キーワード": kws}, ensure_ascii=False, indent=2))
    else:
        report(rows, cx, kws)

    if a.card:
        card = make_card(rows, cx, kws, a.name)
        import os
        os.makedirs(os.path.dirname(a.card) or ".", exist_ok=True)
        with open(a.card, "w", encoding="utf-8") as fh:
            json.dump(card, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"\n型カードを書き出した: {a.card}")
        print("  本文は入っていない。中身は自分のジャンルで一から書くこと。")


def report(rows, cx, kws):
    print(f"\n参考投稿 {cx['posts']}本を分解\n")
    print("─" * 64)
    for r in rows:
        head = "■ " + r["title"]
        if "metrics" in r:
            bits = [f"{k}={v:,}" for k, v in r["metrics"].items()]
            if "like_rate" in r:
                bits.append(f"いいね率{r['like_rate']}%")
            if "slot" in r:
                bits.append("→" + r["slot"] + "枠")
            head += "   " + " ".join(bits)
        print(head)
        print("   フック    " + r["hook"][:46])
        print("   　        " + f"{r['hook_chars']}字 / 型=" + "・".join(r["hook_types"]))
        chars = "→".join(str(c) for c in r["chars_by_slide"])
        print(f"   文字数    {chars} （計{r['chars_total']}字 / 1文{r['sentence_chars_median']}字）")
        print("   仕掛け    " + ("・".join(r["signals"]) or "なし"))
        print("   語尾      " + "・".join(r["endings_top5"]))
        flags = []
        if r["has_cta"]:
            flags.append("CTAあり")
        if r["questions_to_reader"]:
            flags.append(f"問いかけ{r['questions_to_reader']}回")
        if r["emoji"]:
            flags.append(f"絵文字{r['emoji']}個")
        print("   作法      " + ("・".join(flags) or "装飾なし") + "\n")

    print("─" * 64)
    print("\n【共通していること＝これが伸びてる理由の候補】\n")
    ht = "　".join(h["type"] + h["率"] for h in cx["hook_types"][:4])
    print("  フックの型   " + ht)
    hc = cx["hook_chars"]
    print(f"  フック字数   {hc['min']}〜{hc['max']}字（中央{hc['median']}字）")
    print("  スライド     " + "　".join(f"{s}枚×{c}本" for s, c in cx["slides"]))
    dist = "→".join(str(v["median"]) for v in cx["chars_by_slide"].values())
    print(f"  文字数配分   {dist}（中央値）")
    print("  仕掛け       " + "　".join(s["signal"] + s["率"] for s in cx["signals"][:5]))
    print(f"  作法         CTA{cx['cta率']}　問いかけ{cx['問いかけ']}　絵文字{cx['絵文字']}")
    print("\n【参考アカのジャンル語】※そのまま使わない。同じ役割の自分の語に置き換える")
    print("  " + "　".join(f"{k['word']}({k['posts']}本)" for k in kws[:12]))
    print()


if __name__ == "__main__":
    main()
