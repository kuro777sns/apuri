---
name: threads-engine
description: アカウント定義JSON（accounts/*.json）を1枚読んで、そのアカウントのThreads投稿を生成する汎用エンジン。キャラごとにスキルを作らない。生成後は必ず engine/check_post.py で機械検品し、FAILが出たら書き直してから出す。トリガー：「エンジンで作って」「<アカウント名>で投稿」「accounts/xxx.json で」「検品して」「口調を測り直して」など。
---

# Threads 投稿生成エンジン

キャラごとにスキルを書き分けない。**アカウント＝JSON 1枚、生成ロジック＝このスキル1本。**
新しいアカウントは `accounts/_template.json` をコピーして埋めるだけで増える。

## 1. アカウント定義を読む

`accounts/<name>.json` を読む。指定がなければ `ls accounts/` して選ばせる。
`voice.measured` が空なら生成に入らず、先に口調を実測する（下の「口調を測る」）。

読むべき所と、それが生成の何を決めるか：

| フィールド | 生成で守ること |
|---|---|
| `identity.first_person` / `second_person` | 一人称は固定。`second_person` が `null` なら読者を主語にしない |
| `identity.stance` | 誰の立場から語るか。ここを外すと別人になる |
| `target.situation` | 1枚目でこの場面のどれかを名指しする。抽象テーマから始めない |
| `persona.weakness` | 自白の在庫。1本につき1つ使う。使ったら使用ログに残す |
| `voice.measured.length.chars_by_slide` | **各スライドの文字数をこのレンジに収める**（1枚目と3枚目で狙いが違う） |
| `voice.measured.endings_top10` | 語尾はこの分布に寄せる。全文この語尾にはしない（実測でも2割） |
| `voice.measured.layout` | 1文1行。`blank_line_ratio` の分だけ空行を入れる |
| `voice.rules` | 数値に落ちない言語ルール。全部守る |
| `ng` | 禁止ワード・禁止表現・問いかけ・絵文字。**書いたあとに機械で測られる** |
| `themes` | reach枠 と like枠 は別のネタで作る。`mix` の比率を守る |
| `themes.hook_keywords` | 1枚目に最低1語入れる |
| `funnel` | 全本にCTA。`cta_mix` の配分でローテ。`links` が空ならURLは出さない |
| `output` | スレッド枚数、1スライド＝1コードブロック、ラベル形式 |

`references` が入っていたら、**借りる部位だけ**借りる。3アカを均等に混ぜない。
- `borrow: hook` → 1行目の切り出し方だけ
- `borrow: rhythm` → 文の長さと改行だけ
- `borrow: structure` → 構成の運びだけ
- `borrow: cta` → 締めと導線だけ

中身・体験・思想は本人100%。参考アカの文をそのまま写さない。

## 2. ネタを決める

**伸びを決めるのは口調ではなくネタ。** 口調は差別化であって、伸びの主因ではない。

- `themes.mix`（例 `reach2:like3`）の比率で枠を割る。
- **reach枠**＝数字リスト型。インプレッションと保存が伸びる。
- **like枠**＝誤解訂正・好きの証拠型。いいね率が出る。
- 型は `formats/catalog.json` から選ぶ。`slot` が枠に一致するものを優先。
- **直近2回で使った型は避ける。** 使用ログ（`posts/` の末尾）を見て被りを消す。

## 3. 書く

- 1スライド＝1コードブロック。コードブロックの中は投稿本文だけ。
- ラベル（`**1スレッド目 / 全3**`）は**コードブロックの外**に置く。
- スライド番号を本文に書かない。
- 1枚目は助詞や読点で未完に切って次に送る。
- CTAの直前に救済の一行を置く（`funnel.rules` に指定があればその語で）。
- 読者への問いかけを置かない（`ng.no_questions` が true のとき）。会話の引用「」は残してよい。

## 4. 検品する（省略禁止）

書いたら必ず走らせる。プロンプトに禁止事項を書くだけでは守られない。

```bash
# 下書きを1本チェック
PYTHONPATH=engine python3 engine/check_post.py accounts/yu.json draft.md --md

# 1日分をまとめて検品（### 見出しごとに1本とみなす）
PYTHONPATH=engine python3 engine/check_post.py accounts/yu.json posts/today.md --batch
```

- **FAIL が1件でも出たら出力しない。** 直してから再度かける。
- WARN は理由を説明できるなら残してよい。
- 終了コードは FAIL があれば 1。

## 5. 口調を測る／測り直す

口調は書き換えるものではなく、測り直すもの。実投稿が溜まったら回す。

```bash
# 新規アカウント：参考にする実投稿20〜30本からプロファイルを作る
PYTHONPATH=engine python3 engine/extract_voice.py ref.md --md --name ゆず --handle @x -o /tmp/voice.json

# 既存アカウント：定義の voice.measured を更新
PYTHONPATH=engine python3 engine/update_voice.py accounts/yu.json posts/*.md --md --section 悠
```

実投稿が20本未満のときは数値が暴れる。その場合は `voice.rules` を厚く書いて補う。

## 6. 出したら記録する

`posts/<日付>_<アカウント>.md` に保存し、末尾に使用ログを1行足す。

```
2026-09-10 ｜ 悠 ｜ 型64・型99・型57 ｜ 枠=reach2:like3 ｜ CTA=固定2/プロフ1 ｜ 自白=先に日を押さえる理由がなかった
```

型・自白・CTAの被りはこのログだけで防ぐ。書かないと次回必ず被る。

## やらないこと

- キャラ専用スキルを新規に作る（アカウントはJSONで増やす）
- `voice` に「フランク」「優しい」のような形容詞を書く（数値で書く）
- 参考アカウントの文をそのまま使う（借りるのは構造とリズムだけ）
- 検品を飛ばして出力する
