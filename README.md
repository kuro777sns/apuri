# Threads アカウント設計＆投稿生成エンジン

アカウントの**ターゲット・ペルソナ・禁止事項・口調**を1枚のJSONに定義して、
そこから投稿を生成し、**書いたあとに機械で検品する**ためのツール一式。

キャラごとに生成スキルを書き分けない。**アカウント＝JSON 1枚、生成ロジック＝1本。**
新しいアカウントは JSON を1枚足すだけで増える。

---

## 設計の前提（ここが他と違う）

### 1. 口調は形容詞では再現できない。実測する

口調欄に「フランクで優しい、断定調」と書いてAIに投げても、出てくるのは *平均的なフランク* で、誰の文体でもない。
このツールは実投稿20〜30本から**数値と分布**を取る。

実際に3アカウントを測るとこうなる（本リポジトリの実データ121本から抽出）：

| | 1枚目 | 2枚目 | 3枚目 | 1文 | 語尾top3 | 一人称 | 二人称 |
|---|---|---|---|---|---|---|---|
| 悠 | 103字 | 219字 | 306字 | 20字 | いんよ／だよな／ってる | 俺 | 使わない |
| リョウ | 117字 | 217字 | 289字 | 19字 | んよね／ゃない／いんよ | 俺 | あなた |
| ゆず | 77字 | 169字 | 145字 | 16字 | かった／ゃない／今の夫 | 私 | ほぼ使わない |

「ゆずは短く過去形で書く」「二人称を使うのはリョウだけ」——**この差が口調の正体**で、形容詞では絶対に出てこない。

### 2. 禁止事項は「書く」だけでなく「測る」

プロンプトに禁止事項を並べても守られない。生成したあとに機械判定する。

```
ネタ → 生成 → check_post.py → FAILなら書き直し → 出力
                 ├ 禁止ワード（URL内は数えない）
                 ├ 禁止表現（正規表現）
                 ├ 読者への問いかけ（「」内の会話は除外）
                 ├ 絵文字
                 ├ スライド位置別の文字数レンジ
                 ├ 1行の長さ
                 ├ 定義外の一人称／二人称
                 ├ 1枚目のジャンルキーワード
                 ├ CTAの有無と救済の一行
                 └ 語尾一致スコア（実測top10との一致率）
```

FAILがあれば終了コード1を返すので、生成→検品→再生成が自動で回る。

### 3. 参考にしたい投稿は「分解して数字にする」。中身は借りない

伸びてる投稿を送ると、フック・キーワード・文字数・仕掛けを分解して**骨格だけの型カード**にする。

```bash
PYTHONPATH=engine python3 engine/analyze_buzz.py refs.md --md --card formats/cards/A.json
```

```
■ 型64｜本命と都合のいい女は…   imp=182,000 like=94 いいね率0.052% →reach枠
   フック    男は本命と都合のいい子で、誘い方が違う。
             20字 / 型=対比
   文字数    195→232→324 （計751字 / 1文17字）
   仕掛け    箇条書き・セリフ引用・数字・未完切り・転換

【共通していること＝これが伸びてる理由の候補】
  フックの型   暴露40%　対比20%　看板20%　時間期限20%
  フック字数   20〜27字（中央23字）
  文字数配分   133→232→316（中央値）
  仕掛け       数字100%　未完切り100%　転換100%　セリフ引用80%　箇条書き60%
  作法         CTA100%　問いかけ0%　絵文字0%
```

型カードに**本文は入らない**。入るのは字数・型・仕掛けの分布と、
「参考アカのジャンル語 → 自分のジャンルの語」の置き換え表だけ。
だから恋愛の型をそのまま副業アカや育児アカに持っていける。

指標（`imp=` `like=`）を付けると**リーチ枠といいね枠を自動で分ける**。
上の実例では、インプ18万・24万の本はいいね率0.05%、インプ7千〜1.2万の本はいいね率0.43〜0.55%。
**巨大インプの本といいねが付く本は、別のネタで作られている。**混ぜて分析すると必ず間違える。

### 4. 丸パクリは精神論ではなく機械で止める

生成物と参考投稿の**最長一致文字列**と**5-gram重複率**を測る。

```bash
PYTHONPATH=engine python3 engine/check_post.py accounts/mine.json draft.md --md --against refs.md
```

実データでの校正結果：

| 下書き | 最長一致 | 重複率 | 判定 |
|---|---|---|---|
| 参考投稿そのもの | 713字 | 100% | FAIL |
| **語尾だけ変えた「リライト」** | **205字** | **93%** | **FAIL** |
| 同じ書き手の別テーマの投稿 | 13字 | 6% | PASS |

「リライトしたつもり」が一番危ない。ここが機械で止まる。
借りていいのは *1行目を何字でどう切るか・何枚で何字ずつ配るか・どこで転換するか* まで。

### 5. 参考アカウントは「混ぜる」のではなく「部位を分けて借りる」

3アカウントを均等ブレンドすると、3人の平均＝誰でもない人になる。だから借りる部位を分ける。

| `borrow` | 借りるもの |
|---|---|
| `hook` | 1行目の切り出し方 |
| `rhythm` | 文の長さと改行 |
| `structure` | 構成の運び |
| `cta` | 締めと導線 |

中身・体験・思想は本人100%。参考アカの文そのものは写さない。

### 6. 伸びを決めるのは口調ではなくネタ

口調は差別化であって、伸びの主因ではない。**リーチといいねは別のネタで作られる。**

- **reach枠**＝数字リスト型（「N個」「N段階」「1位」）。インプと保存が伸びる
- **like枠**＝誤解訂正・好きの証拠型（「〜は逆」「半分しか」「本音」）。いいね率が出る

`themes.mix`（例 `reach2:like3`）で1日の本数を割る。`formats/catalog.json` の `slot` がこの枠。

---

## 5分で始める

```bash
# 0. 参考にしたいバズ投稿を分解する（任意・応用したい型があるとき）
PYTHONPATH=engine python3 engine/analyze_buzz.py refs.md --md --card formats/cards/A.json

# 1. アカウント定義を作る
cp accounts/_template.json accounts/mine.json
# → identity / target / persona / ng / themes / funnel を埋める（voice.measured は空のまま）

# 2. 口調を実測して流し込む
#    自分の過去投稿、または参考アカウントの投稿を20〜30本ファイルに貼っておく
PYTHONPATH=engine python3 engine/update_voice.py accounts/mine.json ref.md --md

# 3. 生成する（Claude Code で）
「accounts/mine.json でリーチ枠2本・いいね枠3本」

# 4. 検品する（参考投稿を見て書いたなら --against も付ける）
PYTHONPATH=engine python3 engine/check_post.py accounts/mine.json draft.md --md --against refs.md
```

生成は `.claude/skills/threads-engine/` が担当する。アカウント名を言えば起動する。

---

## ファイル構成

```
accounts/
  _template.json        購入者が埋める雛形（全項目にコメント付き）
  yu.json               悠（@yu.0320.love）    実測39本
  ryo.json              リョウ（@kaihi_ryo）    実測40本
  yuzu.json             ゆず（@yuzu_fukuenlove）実測42本
engine/
  schema/account.schema.json  アカウント定義のスキーマ
  extract_voice.py      実投稿 → 口調プロファイル（実測）
  update_voice.py       アカウント定義の voice.measured を更新
  analyze_buzz.py       参考投稿 → なぜ伸びたかの分解＋骨格だけの型カード
  check_post.py         生成物の機械検品（--against で丸パクリ判定）
formats/
  catalog.json          型カタログ42種（slot＝reach/like付き）
  cards/_sample.json    型カードの実例（本文は入っていない）
.claude/skills/threads-engine/
  SKILL.md              生成エンジン本体
posts/                  出力の保管場所＋使用ログ
```

依存ライブラリなし。Python 3.8+ だけで動く。

---

## コマンド

```bash
# 口調を実測して表示するだけ
PYTHONPATH=engine python3 engine/extract_voice.py ref.md --md --name ゆず --handle @x

# 特定の ## 見出しの節だけ測る（複数キャラが1ファイルに入ってる時）
PYTHONPATH=engine python3 engine/extract_voice.py posts/*.md --md --section 悠 -o voice.json

# アカウント定義に流し込む
PYTHONPATH=engine python3 engine/update_voice.py accounts/yu.json posts/*.md --md --section 悠

# 参考投稿を分解する（imp= like= を書いておくとリーチ枠/いいね枠が出る）
PYTHONPATH=engine python3 engine/analyze_buzz.py refs.md --md
PYTHONPATH=engine python3 engine/analyze_buzz.py refs.md --md --card formats/cards/A.json --name A型

# 下書きを1本検品
PYTHONPATH=engine python3 engine/check_post.py accounts/yu.json draft.md --md

# 丸パクリになっていないか一緒に測る
PYTHONPATH=engine python3 engine/check_post.py accounts/yu.json draft.md --md --against refs.md

# 1日分をまとめて検品（### 見出しごとに1本とみなす）
PYTHONPATH=engine python3 engine/check_post.py accounts/yu.json posts/today.md --batch

# CI や自動ループ用（機械可読）
PYTHONPATH=engine python3 engine/check_post.py accounts/yu.json draft.md --md --json
```

---

## 検品の校正について

チェッカーの閾値は、既存の実投稿42本（PASSすべきもの）と、わざと崩した下書き（FAILすべきもの）の
両方で校正してある。実投稿を流すと大半がPASSし、崩した下書きはFAIL 9件（禁止ワード2・問いかけ2・絵文字・文字数・キーワード欠落・CTA欠落）を返す。

なお、この42本を検品すると **11本がFAILする**。内訳は
「1枚目にジャンルキーワードなし」11件・スライド文字数がレンジ外4件・語尾一致0%が1件。
これはツールの誤検出ではなく、運用ルールに書いてある
「恋愛バズキーワードを1枚目に必ず入れる」を実際に外していた投稿。
人の目で42本を見返しても、まず見つからない類のズレが出る。

---

## やらないこと

- キャラ専用の生成スキルを増やす（アカウントはJSONで増やす）
- `voice` に「フランク」「優しい」のような形容詞を書く（数値で書く）
- 参考アカウントの文をそのまま使う（借りるのは構造とリズムだけ）
- 検品を飛ばして出力する
