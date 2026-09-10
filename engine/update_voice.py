#!/usr/bin/env python3
"""実投稿を読み直して、アカウント定義の voice.measured を更新する。

投稿が溜まったら回す。口調は書き換えるものではなく、測り直すもの。

使い方:
    python3 engine/update_voice.py accounts/yu.json posts/*.md --md --section 悠
"""
import argparse
import json
import sys

from extract_voice import analyze, blocks_from_md, blocks_from_plain


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("account")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--section")
    a = ap.parse_args()

    acc = json.load(open(a.account, encoding="utf-8"))
    blocks = []
    for f in a.files:
        text = open(f, encoding="utf-8").read()
        blocks += blocks_from_md(text, a.section) if a.md else blocks_from_plain(text)
    if not blocks:
        sys.exit("投稿が1本も取れなかった")

    prof = analyze(blocks, acc["identity"]["name"], acc["handle"])
    for k in ("name", "handle"):
        prof.pop(k)
    acc.setdefault("voice", {})["measured"] = prof
    with open(a.account, "w", encoding="utf-8") as fh:
        json.dump(acc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    m = prof["length"]
    print(
        f"{a.account}: {prof['measured_from']['blocks']}本 / "
        f"{prof['measured_from']['sentences']}文から更新\n"
        f"  1スレッド {m['chars_per_thread']['p25']}〜{m['chars_per_thread']['p75']}字"
        f"（中央 {m['chars_per_thread']['median']}）\n"
        f"  語尾top3 {[e['tail'] for e in prof['endings_top10'][:3]]}"
    )


if __name__ == "__main__":
    main()
