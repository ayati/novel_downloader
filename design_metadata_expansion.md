# 設計書：配信元メタデータの拡充と ePub3 書誌への反映

- 対象: `novel_downloader.py`（全17サイト）＋ `yomikake.html` / `yomikake_ios.html`
- 関連: yomikake `design_bibliography_v2.md`（v2.11.0・書誌ブロック実装済み）
- ステータス: **設計確定・実装待ち**
- 調査日: 2026-07-26。実サイトの HTML / API を実取得し、現行コードは行番号まで確認した
- 方針の要: **ジャンルは粗く**（yomikake の母数は1〜3桁。サイト側の6〜8桁向け分類をそのまま持ち込まない）

---

## 1. 現行コード確認結果（実測）

### 1.1 あらすじは16/17サイトで既に取得済み

`aozora_header()` と `build_epub()` の両方に渡っており、`dc:description` にも出ている。
未対応は**青空文庫のみ**（`run_aozora()` `:7592` が `build_epub(..., "", ...)` とハードコード）。
以下は品質不具合として実測で確認したもの。

| # | 症状 | 場所 | 原因と対処 |
|---|---|---|---|
| **A** | アルファポリスのあらすじで**段落改行が失われる** | `alp_get_work_info()` `:3385` | `<meta name="description">` は `<br>` が空白に潰れている。本文 `div.p-content-info__abstract` から取れば改行が残る |
| **B** | 青空文庫だけあらすじが空 | `run_aozora()` `:7592` | 図書カードの「作品について」欄を読んでいない |
| **C** | 杉田玄白のあらすじ欄に**原題（英語）**が入る | `genpaku_get_work_info()` `:6555` | `description` に `original_title` を代入。原題は subtitle 相当 |
| **D** | NOVEL DAYS のあらすじが**空行だらけ**（実測: 23行中15行が空行、3連続以上の空行4箇所） | `days_get_work_info()` `:6269` | サイトが `<br>` を段落間に2〜4個並べている。**全サイト共通の正規化が必要** |
| **E** | 青空文庫のカードページが**丸ごと文字化け**し、タイトル・著者が取れない | `aozora_fetch_html()` `:7123` | サーバが `Content-Type` に charset を付けず、`shift_jis` へフォールバックしていた。サイトは UTF-8 化済み。`<meta charset>` を見て判定する |
| **F** | 青空文庫の著者にナビゲーションの**「作家別作品リスト」**が入る | `aozora_get_work_info()` `:7160` | `index_pages/person` への最初のリンクを拾っていた。E を直すと文字化けが解けて誤った名前が表示されるようになるため同時に対処が必要 |

> **A の訂正**: 当初「meta は148字で切り詰められる」と記載したが、これは誤りだった。2作品で実測したところ
> meta・本文 abstract・JSON-LD の**内容は空白差を除いて完全に一致**しており（148字の作品／229字の作品）、
> 末尾の `...` は著者自身が書いた省略記号だった。切り詰めは起きていない。実際の差は改行の有無のみ。

D は yomikake の3行クランプ（`-webkit-line-clamp:3`）と相性が悪く、**空行だけが見える**。
サイト個別ではなく共通ヘルパー `_normalize_synopsis()`（`\n{3,}` → `\n\n`、行末空白除去、前後 strip）で処理する。

### 1.2 `--from-file` であらすじに「底本URL：」行が混入する（既存バグ）

`aozora_header()` `:246` は `【あらすじ】` の**後ろ**に `底本URL：` を置く。一方 `parse_aozora_text()` `:7607`
は区切り線に当たるまであらすじの取り込みを続けるため、実行結果は次のとおり。

```
SYNOPSIS='あらすじ1行目\nあらすじ2行目\n底本URL：https://ncode.syosetu.com/n0022gd/'
```

`--from-file` / `--append` の再生成のたびに表紙ページと `dc:description` に URL 行が混ざる。
**§4 のヘッダー拡張は同じ箇所を触るので、同時に直す。**

### 1.3 `--append` / `--resume` はヘッダーを毎回作り直す（＝メタ行は自動で最新化される）

確認した流れ（`run_narou()` `:2740` ほか全スクレイパー共通）:

```
run_*() → 作品情報を再取得 → header = aozora_header(...)   ← 毎回新規生成
        → _apply_resume() で既存 .txt の「本文セクション」だけ読み込む
        → write_file(txt_path, header, sections, colophon)  ← ヘッダーは新しいものを書く
```

`_load_existing_txt()` `:341` は**2本目の区切り線**を探して本文開始位置を決める（`content.find(SEP)` ×2）。
したがって**ヘッダーに行を増やしても既存 .txt の読み込みは壊れない**し、追記のたびにジャンル・タグ・
話数・更新日が**最新の値に書き換わる**。これは設計上ありがたい性質で、追加のマージ処理は不要。

### 1.4 `parse_epub()` は OPF のメタデータをほとんど読んでいない

`parse_epub()` `:8065` が OPF から読むのは `dc:title` と `dc:creator` だけ。あらすじは
**表紙 XHTML から** `_epub_cover_to_synopsis()` で、底本 URL / サイト名は奥付 XHTML から
`_epub_colophon_to_source()` で復元している。`dc:description` / `dc:source` / `dc:publisher` は無視。

→ `--from-epub` の往復でメタを保つには、**OPF 直読みを主・XHTML 復元をフォールバック**に変更する。

### 1.4b 青空文庫の図書カードに「あらすじ」欄は存在しない

設計初版では「作品について」欄をあらすじとして使えると書いたが、実測するとこの欄の中身は
**Wikipedia へのリンク**だった（走れメロス・ドグラ・マグラ・あばばばば・駈込み訴え＝リンクのみ）。
ただし**初出などの注記がリンクと併記されている作品がある**（こゝろ＝「1914（大正3）年4月20日～
8月11日まで、朝日新聞に連載。」）。したがって方針は「リンクを除いた地の文だけを拾い、無ければ空のまま」。
**あらすじが埋まる作品は少数**である点を織り込んでおく。

### 1.5 `novel_health_check.py` は dry-run の stdout を正規表現で読んでいる

`_EPISODE_PATTERNS`（8パターン）と `re.search(r"タイトル\s*[：:]\s*(.+)", stdout)` `:151`。

- dry-run 出力に**行を足すのは安全**（既存パターンは行頭アンカーを持たないが、別行なので競合しない）。
- ただし **「タイトル」という文字列を含む新ラベルを作ってはいけない**。`原タイトル：〜` を足すと
  `タイトル\s*[：:]` が先にマッチして title が壊れる。原題は `原題：` とする。
- dry-run にジャンル・話数・更新日を出せば、**メタ取得の劣化もヘルスチェックで検知できる**ようになる
  （`_EPISODE_PATTERNS` に頼らずに済むので、将来的な安定化にもつながる）。

### 1.6 青空文庫テキストへの行挿入は「区切り線がある場合のみ」に限る

`_aozora_insert_source_url()` `:7424` は著者行の直後に `底本URL：` を差し込み、
`aozora_text_to_episodes()` `:7456` は「著者行の次 〜 2本目の区切り線」をスキップして本文を得る。
記号説明ブロック（`-----` 2本）がある作品では安全だが、**それが無い作品では挿入行が本文に混入する**
（現行の `底本URL：` 行も同じリスクを負っている）。メタ行を増やすと影響が拡大するため、
**区切り線を検出できたときだけメタブロックを挿入する**ガードを入れる。

### 1.6b `argparse.Namespace` が4箇所で引数を明示列挙している（Phase 3 の地雷）

`--check-update` / `--append` / `--watch` の内部ランナー呼び出しは、`args` を手で組み立てている。

| 行 | 用途 |
|---|---|
| `:8918` | `_check_update_one()` |
| `:9007` | `_append_one()` |
| `:9185` | `_check_update_url()`（watch 用） |
| `:9421` | `run_watch()` の新規ダウンロード |

いずれも `url=` `output=` `delay=` … と**全フィールドを列挙**しており、`--dry-run` 追加時にも
4箇所すべてに `dry_run=False` が足されている。**CLI オプションを1つ足すたびに4箇所の修正が必要**で、
足し忘れると `getattr(args, "xxx", default)` の既定値に化けて静かに壊れる。

→ **Phase 2 で `_make_runner_args(**overrides)` を導入する**。パーサの既定値
（`parser.parse_args([])` 相当の Namespace）を土台にして上書きだけを受け取る形にすれば、
以後オプションを足しても4箇所は無修正で済む。Phase 3 でジャンル関連のオプションを足す前に必要。

### 1.6c `_SITE_DISPATCH` は3要素タプルで5箇所からアンパックされている

`label, default_color, runner = entry` が `:8915` `:9004` `:9183` `:9984` の4箇所、
`entry[1]` が `:9955` の1箇所。**要素数を変えると5箇所すべてが壊れる**。

→ サイト固有のメタ設定（ジャンル辞書の参照先など）は `_SITE_DISPATCH` を拡張せず、
**別テーブル `_SITE_META: dict[str, dict]` を新設**して site ID で引く。既存構造には触らない。

### 1.7 `info` 辞書のキーが不統一

15サイトが `description`、**ネオページだけ `synopsis`**（`neopage_get_work_info()` `:4348`、
呼び出し側 `:4533` `:4576`）。monogatary はそもそも dict を使わずローカル変数。
共通スキーマ化のついでに `description` へ寄せる（`synopsis` キーは互換のため当面併記）。

### 1.8 引数がすでに限界

`build_epub()` `:2177` は位置引数7＋キーワード8、`_make_opf()` `:1581` は9個。
**これ以上フラット引数を足さない**。`meta: dict = None` を1個追加して、その中に入れる。

---

## 2. 各サイトから取れるメタデータ（実測）

`◎`＝実取得して確認 / `○`＝ページ上に存在を確認 / `—`＝無い or 未確認。

| サイト | あらすじ | キャッチ | ジャンル | タグ | 連載状態 | 公開日 | 更新日 | 話数 | 文字数 | 年齢制限 | 取得方法 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| なろう | ◎ | — | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | **公式API** |
| カクヨム | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | `__NEXT_DATA__`（取得済み） |
| monogatary | ◎ | — | ◎ | — | ◎ | ◎ | ◎ | ◎ | — | ◎ | **公式API**（取得済み） |
| アルファポリス | ◎ | — | ◎ | ◎ | ◎ | ○ | ◎ | ○ | ◎ | ◎ | JSON-LD＋本文 |
| ノベルアップ＋ | ◎ | — | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | 「作品情報」表 |
| NOVEL DAYS | ◎ | — | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | ◎ | — | 詳細 `<dl>` |
| エブリスタ | ◎ | ◎ | ◎ | ◎ | ◎ | ○ | ○ | ◎ | — | — | Nuxt SSR |
| 青空文庫 | ○ | — | ○(NDC) | — | — | ○ | ○ | — | — | — | 図書カード（§2.3） |
| 野いちご / berry's / ノベマ！ / ネオページ / ソリスピア / ステキブンゲイ / ハーメルン | ◎ | — | ○ | ○ | ○ | ○ | ○ | ○ | — | ○ | **要追加調査** |
| 杉田玄白 / 結城浩 | △(1.1C) | — | — | — | — | — | — | — | — | — | 訳者・CCライセンスあり |

### 2.1 なろう（`api.syosetu.com`）

現在は作品情報ページを `NarouInfoParser`（`HTMLParser`）で解析している。**公式 API が1リクエストで返す**:

```
title / writer / story(あらすじ) / biggenre / genre / keyword(空白区切りタグ)
general_firstup / novelupdated_at / updated_at / noveltype(1=連載 2=短編)
end(0=完結 1=連載中) / general_all_no(話数) / length(総文字数) / isr15 / isbl / isgl
```

`?out=json&ncode=NXXXX&of=t-w-s-bg-g-k-nt-e-ga-l-gf-nu-ir` でフィールドを絞れる。
HTML より軽く壊れにくい。R18 作品は `novel18api` と別エンドポイントなので、**404/0件なら従来の HTML 解析に
フォールバック**する（挙動が変わらないことを保証）。

### 2.2 カクヨム（既に読んでいる `Work:` オブジェクト）

`kky_get_work_info()` `:2948` が触っている同じ dict に、未使用のフィールドが揃っている（実測）:

```
catchphrase / genre(enum) / tagLabels[] / serialStatus(RUNNING|COMPLETED)
publishedAt / lastEpisodePublishedAt / publicEpisodeCount / totalCharacterCount
isCruel / isViolent / isSexual / ogImageUrl / baseColor / publicationLabelName
```

**追加のリクエストはゼロ**。`baseColor`（作品テーマ色）は表紙背景色に流用できる（現在はサイト共通 `#4BAAE0`）。

### 2.3 青空文庫の図書カード

| カード上の項目 | ePub での使い道 |
|---|---|
| 作品について | **`dc:description`（1.1B の解消）** |
| 作品名読み / 著者名読み・ローマ字 | `refines` の `file-as` → 本棚の著者ソート |
| 分類（NDC 913 等） | `dc:subject` + `authority=NDC` |
| 底本 / 出版社 / 初版発行日 / 入力に使用した版 | `dc:source`（現在は URL のみ） |
| 入力者 / 校正者 | **`dc:contributor` role=`trc` / `pfr`**（MARC relator に実在） |
| 初登録日 / 最終更新日 | `dc:date` / `nd:sourceUpdated` |
| 生没年 | `dc:rights`（著作権消滅の根拠） |
| 文字遣い種別（新字新仮名 等） | `nd:orthography` |

---

## 3. 共通ジャンル軸（本設計の中核）

### 3.1 方針

yomikake の蔵書は1〜3桁。サイト側の細分類（なろう小ジャンル約30種、カクヨム enum、各サイト独自語彙）を
そのまま持ち込むと、**1冊しかない分類が並ぶだけで絞り込みの用をなさない**。したがって:

- **`nd:genre` に「共通ジャンル」1個**（下記10種のいずれか）… yomikake の分類・絞り込みはこれだけを使う
- **`dc:subject` にサイト原文をそのまま**（「ハイファンタジー」「創作論・評論」等）… 書誌ブロックの表示用
- 正規化は **novel_downloader 側で行う**（辞書を JS と二重管理しない）

### 3.2 共通ジャンル 10 種（確定案）

| ID | 表示名 | 主な流入元 |
|---|---|---|
| `fantasy` | ファンタジー | なろう biggenre=2、カクヨム FANTASY、異世界〔恋愛〕以外の異世界もの |
| `romance` | 恋愛 | なろう biggenre=1、カクヨム LOVE/ROMANCE、野いちご・berry's・ノベマ！の大半 |
| `sf` | SF | なろう biggenre=4、カクヨム SF |
| `mystery` | ミステリー・ホラー | ミステリー／サスペンス／ホラー／怪異を統合（単独では母数が薄い） |
| `drama` | 現代ドラマ | 現代もの・青春・お仕事・日常 |
| `history` | 歴史・時代 | 歴史／時代／戦記 |
| `literature` | 文芸 | なろう biggenre=3、純文学・詩・短編集 |
| `nonfiction` | 評論・エッセイ | 創作論・評論・ノンフィクション・エッセイ、杉田玄白／結城浩の翻訳 |
| `fanfic` | 二次創作 | ハーメルン、カクヨム FAN_FICTION、`fanFictionSource` あり |
| `other` | その他 | 上記に落ちないもの・ノンジャンル・判定不能 |

- **ミステリーとホラーを統合**した（それぞれ単独だと蔵書2〜3冊にしかならない想定）。
- 二次創作は独立させた（性格が大きく違い、絞り込みたい需要が明確なため）。
- **判定できないときは `other` ではなく `nd:genre` を出さない**。「その他」は「そう分類された」場合のみ。

### 3.3 マッピングの持ち方

`_GENRE_MAP: dict[str, dict[str, str]]` をサイトIDごとに持つ。

```python
_GENRE_MAP = {
    "narou":    {"1": "romance", "2": "fantasy", "3": "literature",
                 "4": "sf", "98": None, "99": "other"},          # biggenre で判定
    "kakuyomu": {"FANTASY": "fantasy", "LOVE": "romance", ...},   # enum
    "days":     {"創作論・評論": "nonfiction", ...},              # 原文文字列
}
```

- なろうは**小ジャンル（`genre`）ではなく大ジャンル（`biggenre`）で判定**する。粗く分けるという方針そのもの。
  ただし `dc:subject` には小ジャンル名を入れる（小ジャンルコード表は API ドキュメント準拠で別途作成）。
- カクヨムの enum は実測で `FANTASY` のみ確認済み。**残りは実装時に各ジャンルの作品ページで実値を確認する**
  （推測で表を書かない）。
- 未知の値が来たら `None`（＝ `nd:genre` を出さない）＋ stderr に1行警告。辞書の陳腐化に気づける。
- サイトにジャンル概念が無い場合（青空文庫・杉田玄白・結城浩）は NDC や既定値から埋める。
  青空文庫は NDC 上位1桁（9=文学 → `literature`）で十分。

---

## 4. `.txt` ヘッダーの拡張（先に固める基盤）

ePub は `--from-file` / `--append` でテキストから作り直される。テキストにメタが無ければ再生成で消える。

### 4.1 出力形式（確定案）

```
水属性の魔法使い
久宝　忠

底本URL：https://ncode.syosetu.com/n0022gd/
配信元：小説家になろう
ジャンル：ファンタジー（ハイファンタジー）
タグ：異世界転生 男主人公 魔法 冒険
状態：完結
公開日：2020-04-01
更新日：2026-07-15
話数：935
文字数：4074034
年齢制限：R15

【あらすじ】
……
-------------------------------------------------------
【テキスト中に現れる記号について】
```

- **`【あらすじ】` より前に置く**。後ろに置くと §1.2 のとおり全部あらすじに吸い込まれる。
- ラベルは既存 `底本URL：` と同じ全角コロン体裁。読み物としても自然に読める。
- `ジャンル：` は **`共通ジャンル（サイト原文）`** の形。共通軸と原文の両方を1行で往復できる。
- **値が取れなかった行は出さない**（行の有無で判定するため、空値行を作らない）。
- 既存 `.txt` には行が無いだけ＝前方互換。`--append` 時に §1.3 のとおり自動で書き直される。

### 4.2 パーサ側の変更

| 関数 | 変更内容 |
|---|---|
| `aozora_header()` `:246` | `meta: dict = None` を追加。あらすじブロックの**前**にメタ行を組み立てる |
| `parse_aozora_text()` `:7607` | **`in_synopsis` 中に `^[^\s：]{1,12}：` の行が来たらあらすじを打ち切る**（§1.2 の修正）。同じループでメタ行を辞書に収集し、戻り値を `(title, author, synopsis, episodes, meta)` の5要素へ拡張 |
| 新設 `_extract_meta_from_txt()` | `_extract_url_from_txt()` `:410` の一般化。全文正規表現なので**行の順序に依存しない** |
| `_aozora_insert_source_url()` `:7424` | メタブロックも挿入。**区切り線を検出できたときだけ**（§1.6） |
| `parse_epub()` `:8065` | OPF から `dc:description` / `dc:subject` / `dc:publisher` / `dc:source` / `nd:*` を直読み。XHTML 復元はフォールバックに降格（§1.4） |
| `run_from_file()` `:7699` | `parse_aozora_text()` の meta を `build_epub(meta=...)` に渡す |

---

## 5. ePub 3.2 側のマッピング

`<package prefix="nd: https://github.com/ayati/novel_downloader/ns#">` を1行足して独自項目を `nd:` に集約する。
`dcterms:` `marc:` `schema:` は EPUB 3 の予約プレフィックスなので宣言不要。

### 5.1 標準要素

| 情報 | OPF 表現 |
|---|---|
| あらすじ | `<dc:description>`（実装済み。§1.1 を修正） |
| キャッチコピー | `<dc:title id="sub">` ＋ `<meta refines="#sub" property="title-type">subtitle</meta>`（既存 title に `main` を付与） |
| ジャンル原文・タグ | `<dc:subject>` を複数（タグは10件で打ち切り） |
| NDC | `<dc:subject id="ndc">` ＋ `refines` の `authority=NDC` / `term` |
| **作品の初回公開日** | `<dc:date>` … **生成日をやめる**（§5.3） |
| 訳者・入力者・校正者 | `<dc:contributor>` ＋ role `trl` / `trc` / `pfr` |
| タイトル読み・著者読み | `refines` の `file-as` |
| 年齢制限 | `<meta property="dcterms:audience">R15</meta>` |
| シリーズ | `belongs-to-collection` ＋ `collection-type="series"` |
| ライセンス | `<dc:rights>`（青空文庫＝著作権消滅、結城浩＝CC。ページから取得可能） |

### 5.2 `nd:` 独自メタ

| property | 例 | yomikake での用途 |
|---|---|---|
| `nd:genre` | `fantasy` | **本棚のジャンル分け（本設計の主目的）** |
| `nd:serialStatus` | `完結` / `連載中` | 状態バッジ |
| `nd:episodeCount` | `935` | 「935話中148話を収録」 |
| `nd:characterCount` | `4074034` | 読了目安時間の算出 |
| `nd:sourceUpdated` | `2026-07-15` | 「サイト更新が新しい順」ソート |
| `nd:downloadedAt` | ISO8601 | いつ時点のスナップショットか |
| `nd:siteId` | `narou:n0022gd` | 同一作品の重複検出 |
| `nd:contentWarning` | `暴力表現,性的表現` | 表示前の注意 |
| `nd:orthography` | `新字新仮名` | 青空文庫のみ |

### 5.3 `dc:date` の是正

現在 `dc:date` = ePub 生成日。yomikake 書誌 v2 は「`dc:date` == `dcterms:modified`（±1日）なら生成日」と
みなして**表示を抑止**しており、設計書に「実測7/17冊が旧 novel_downloader / 旧 jisui2epub の出力」とある。

| 要素 | 入れる値 |
|---|---|
| `dc:date` | **作品の初回公開日** |
| `dcterms:modified` | ePub 生成時刻（必須要素・現行どおり） |
| `nd:sourceUpdated` | サイト側の最終更新日 |
| `nd:downloadedAt` | ダウンロード実行日時 |

既存 ePub は生成日のままなので、**yomikake 側の抑止ロジックは削除しない**。

### 5.4 アクセシビリティ metadata（ついで）

テキストのみなので全サイト共通の固定値を出せる。jisui2epub は既に出力済みで、揃えると3ツールの水準が合う。

```
schema:accessMode = textual
schema:accessModeSufficient = textual
schema:accessibilityFeature = readingOrder / tableOfContents / structuralNavigation
schema:accessibilityHazard = none
schema:accessibilitySummary = 本文はテキストのみで構成されています。
```

挿絵を含む青空文庫作品のみ `accessibilityFeature` を調整する。

---

## 6. novel_downloader 側の実装方針

### 6.1 共通スキーマ

`*_get_work_info()` の戻り値を次に寄せる。**全部揃わなくてよい**（取れたら入れる）。

```python
{
  "title": str, "author": str, "description": str,
  # 以下すべて任意
  "catchphrase": str, "genre": str,          # genre = 共通ジャンルID（§3.2）
  "genre_raw": str, "tags": [str],
  "serial_status": str, "published": "YYYY-MM-DD", "updated": "YYYY-MM-DD",
  "episode_count": int, "char_count": int,
  "age_rating": str, "content_warnings": [str],
  "cover_url": str, "theme_color": "#RRGGBB", "series": str,
  "site_id": str, "rights": str,
  "contributors": [{"name": str, "role": "trl"}],
  "title_kana": str, "author_kana": str, "orthography": str,
}
```

- `aozora_header(title, author, synopsis, source_url, meta=None)`
- `build_epub(..., meta=None)` → `_make_opf(..., meta=None)`

**位置引数は増やさない**（§1.8）。既存の呼び出し17箇所は `meta=info` を足すだけで済む形にする。

### 6.2 サイトごとの作業量

| 規模 | 対象 | 内容 |
|---|---|---|
| 小 | カクヨム / monogatary | **既に読んでいる JSON から拾うだけ**。追加リクエストなし |
| 小 | アルファポリス | §1.1A の修正＋JSON-LD の `genre` |
| 小〜中 | なろう | API 化（失敗時は現行 HTML 解析にフォールバック）＋大ジャンル辞書 |
| 中 | ノベルアップ＋ / NOVEL DAYS | 定義リスト（`<dl>` / `<table>`）を舐める汎用ヘルパーを1本書いて共用 |
| 中 | エブリスタ | Nuxt SSR の DOM からタグ・ジャンル・完結ラベル |
| 中 | 青空文庫 | 図書カードの `<table>` 解析（§2.3）。効果が大きい |
| 未調査 | 野いちご・berry's・ノベマ！・ネオページ・ソリスピア・ステキブンゲイ・ハーメルン | 実ページで要確認。**ジャンルだけ先に拾う** |
| 別枠 | 杉田玄白 / 結城浩 | §1.1C 修正、訳者を contributor へ、CC を `dc:rights` へ |

### 6.3 dry-run 出力とヘルスチェック

`_dry_run_exit()` `:323` の前に出しているタイトル・話数の並びに、取れたメタを追記する。

```
  タイトル : 水属性の魔法使い
  作者     : 久宝　忠
  総話数   : 935 話
  ジャンル : ファンタジー（ハイファンタジー）      ← 追加
  状態     : 完結 / 更新 2026-07-15                ← 追加
```

- **「タイトル」を含むラベルを新設しない**（§1.5）。原題は `原題：`。
- 将来 `novel_health_check.py` 側に「ジャンルが取れているか」の検査を足せる（今回はスコープ外）。

---

## 7. yomikake 側

### 7.1 書誌ブロック（v2.11.0 の器をそのまま使う）

```
現在の本
水属性の魔法使い
 　剣と魔法の世界に転生することになった…            ← subtitle（キャッチコピー）
著者 久宝　忠 🔍
出版社：小説家になろう          [完結]              ← nd:serialStatus をバッジ表示
刊行：2020年4月1日 ／ サイト更新：2026年7月15日      ← dc:date / nd:sourceUpdated
ジャンル：ファンタジー
#異世界転生 #魔法 #冒険                             ← dc:subject をチップ表示
底本：小説家になろうで読む ↗
あらすじ：……（3行クランプ・実装済み）
935話中 148話を収録 ／ 約407万字 ／ 読了目安 約13時間
```

- **収録話数と `nd:episodeCount` の差**は yomikake 単体では作れない情報。novel_downloader と組にする最大の利点。
- 読了目安は `nd:characterCount ÷ 500字/分`。既存の「時間で並べ替え」（`design_time_left_sort.md`）と噛み合う。

### 7.2 本棚 / 読みかけリスト（本命）

- **ジャンル分け**：`nd:genre` の10種で絞り込み。蔵書100冊でも各ジャンル数冊〜20冊に収まる粒度。
- 完結／連載中バッジ（積読の優先度判断に直結）。
- タグをタップ → 同じタグの本だけ表示。
- 著者名ソート（`file-as`）。設計書 §7 の将来課題の回収。
- 「サイト更新が新しい順」ソート（`nd:sourceUpdated`）。

### 7.3 実装上の注意

- **`makeBookKey()` は変えない**。`dc:creator` に訳者・入力者を混ぜない（§8）。
- 追加 state は表示専用（`bookGenre` / `bookTags` / `bookSerialStatus` / `bookEpisodeCount` /
  `bookCharCount` / `bookSourceUpdated`）。`closeBook()` のリセットにも漏れなく追加。
- `nd:` メタは `metadata meta[property="nd:xxx"]` の**文字列一致**で読む（`querySelector` は名前空間解決しない）。
- i18n 4言語。**共通ジャンル名だけ翻訳し、タグとジャンル原文は原文のまま**出す。
- PC 版 / iOS 版の両ファイルに同一差分。

---

## 8. リスクと非目標

- **しおり互換**：`dc:creator` を変えると `makeBookKey` が変わり既存しおりが割れる。杉田玄白・結城浩の
  「原著者（訳者 訳）」を contributor へ分離すると**その2サイトの既存 ePub のしおりは割れる**。
  価値はあるが Phase 6 に回し、リリースノートで明示する。
- **epubcheck**：`prefix` 宣言と `refines` の id 参照でミスしやすい。Phase 4 で必ず通す。
- **スクレイピング脆弱性**：メタは全部「取れたら入れる」。取れないことをエラーにしない。
  ジャンル辞書に未知の値が来たら警告だけ出して `nd:genre` を省略する。
- **やらないこと**：ブックマーク数・PV・レビュー点などの**人気指標は入れない**（読書の役に立たず、
  ダウンロード時点で陳腐化する）。ASIN 相当の出自情報も入れない（yomikake 側の判断と揃える）。

---

## 9. 実装順

| Phase | 内容 | 備考 |
|---|---|---|
| **1** | §1.1 A〜F＋§1.2 のバグ修正。`_normalize_synopsis()` 新設。青空文庫のあらすじ対応 | **v2.3.1 でリリース済み** |
| **2** | 共通スキーマ、`meta` 引数の配管、`.txt` ヘッダー拡張、`parse_aozora_text` 5要素化、`_extract_meta_from_txt`、`--from-epub` の OPF 直読み、`_make_runner_args()` | **実装済み**（`nd:` の OPF 出力も込み・下記） |
| **3** | 共通ジャンル辞書（§3）＋カクヨム・monogatary・アルファポリス・なろうのメタ取得 | **実装済み**（§10.2b） |
| **4** | OPF 出力（subtitle / dc:subject / dc:date 是正 / contributor / audience / a11y / `nd:`）＋ epubcheck | |
| **5** | yomikake 書誌ブロック拡張（§7.1） | |
| **6** | 残りサイトのメタ取得＋青空文庫の図書カード書誌＋訳者の contributor 分離 | |
| **7** | yomikake 本棚のジャンル絞り込み・状態バッジ・著者ソート（§7.2） | **最終的な成果はここ** |

Phase 3 以降はサイト単位で分割リリースできる。

---

## 10. Phase 2〜4 実装設計（現行コード確認済み）

### 10.1 Phase 2: 配管（先に通す）

**触る関数と変更内容**

| 関数（現在地） | 変更 |
|---|---|
| `aozora_header()` `:262` | 第5引数 `meta: dict = None` を追加。メタ行は **`【あらすじ】` の前**に組み立てる（§1.2） |
| 新設 `_format_meta_lines(meta)` | `meta` → `["配信元：…", "ジャンル：…", …]`。**値が空のキーは行ごと出さない** |
| 新設 `_parse_meta_lines(text)` | ヘッダー文字列 → `meta` dict。`_extract_url_from_txt()` `:410` と同じく**全文正規表現で順序非依存** |
| `parse_aozora_text()` `:7680` | 戻り値を **5要素** `(title, author, synopsis, episodes, meta)` へ。**呼び出しは `:7809` の1箇所だけ**なので低リスク |
| `build_epub()` `:2178` | キーワード引数 `meta: dict = None` を追加（位置引数は増やさない・§1.8） |
| `_make_opf()` `:1581` | 同上。metadata ブロックの生成を `meta` から組み立てる（Phase 4 で中身を足す） |
| `_make_cover_xhtml()` `:1310` | キャッチコピーを表紙に出すなら `subtitle` を追加。**Phase 4 と同時でよい** |
| `run_from_file()` `:7772` | `parse_aozora_text()` の `meta` を `build_epub(meta=…)` へ渡す |
| `run_from_epub()` `:8350` | `parse_epub()` の `meta` を `aozora_header(meta=…)` へ渡す |
| `parse_epub()` `:8138` | OPF から `dc:description` / `dc:subject` / `dc:publisher` / `dc:source` / `nd:*` を直読み。現行の XHTML 復元（`_epub_cover_to_synopsis` / `_epub_colophon_to_source`）は**フォールバックに降格**（§1.4） |
| `_aozora_insert_source_url()` `:7497` | メタブロックも挿入。**区切り線を検出できたときだけ**（§1.6） |
| 新設 `_make_runner_args(**overrides)` | §1.6b。4箇所の `argparse.Namespace` を置き換える |
| 新設 `_SITE_META` | §1.6c。`_SITE_DISPATCH` は触らない |

**実装時の判断（2026-07-26）**

- **`nd:` の OPF 出力は Phase 4 から Phase 2 に前倒しした。** `.txt` → ePub → `.txt` の往復で
  メタが保存されることが Phase 2 の受け入れ条件だが、その保存先が OPF なので分離できない。
  Phase 4 に残るのは**標準語彙**（subtitle / `dc:subject` / `dc:date` 是正 / contributor /
  `dcterms:audience` / アクセシビリティ）のみ。
- `prefix="nd: …"` の宣言は **`nd:` を実際に1件以上出すときだけ**付ける。メタ未取得のサイトでは
  OPF が従来とバイト単位で同一になり、既存の挙動を変えない。
- 底本URL は `_META_FIELDS` に入れず、従来どおり独立した `底本URL：` 行のままにした。
  `_extract_url_from_txt()` と `--append` / `--check-update` が依存しているため。
  `run_from_file()` はヘッダーから直接この行を拾って `dc:source` に戻す。
- タグ区切りは**全角スラッシュ `／`**。タグ自体に空白を含むサイトがあるため空白区切りにはしない
  （設計初版の例は空白区切りだったが往復の安全側に倒した）。`nd:tags` はカンマ区切り。

**回帰確認（Phase 2 の必須項目）**

1. メタ行が**無い**既存 `.txt` → `--from-file` が従来どおり動く（前方互換）
2. メタ行が**ある** `.txt` → `--from-file` → ePub → `--from-epub` → `.txt` でメタが保存される
3. `--append` で既存 `.txt` のヘッダーが最新のメタ付きに置き換わる（§1.3）
4. 区切り線の無い青空文庫作品でメタ行が本文に混入しない
5. `novel_health_check.py` 17/17

### 10.2 Phase 3: ジャンル取得

**作業順**（低コスト順。1サイトずつ動作確認して進める）

1. `_GENRE_MAP` と正規化関数 `_normalize_genre(site, raw) -> str | None`（§3.3）
2. **カクヨム** — `kky_get_work_info()` `:2948` が既に持っている `Work` dict から
   `catchphrase` / `genre` / `tagLabels` / `serialStatus` / `publishedAt` /
   `lastEpisodePublishedAt` / `publicEpisodeCount` / `totalCharacterCount` /
   `isCruel` / `isViolent` / `isSexual` / `baseColor` を拾う。**追加リクエストなし**
3. **monogatary** — 既に読んでいる API JSON から `genre` / `theme` / `isFinished` /
   `publishAt` / `storyUpdatedAt` / `readingTime` / `overFifteen`
4. **アルファポリス** — JSON-LD `Article.genre` ＋ 本文のタグリンク・`文字数`・`更新日時`
5. **なろう** — `api.syosetu.com` へ切り替え。`narou_get_novel_info()` `:2448` を
   API 版に置き換え、**失敗時は現行の `NarouInfoParser` にフォールバック**（挙動を変えない）。
   `narou_get_all_episodes()` `:2541` の戻り値は4要素タプル → `meta` を足して5要素にする

**dry-run 出力への追記**（§6.3）。`novel_health_check.py` の
`re.search(r"タイトル\s*[：:]\s*(.+)")` に食われるため、**新ラベルに「タイトル」を含めない**。

### 10.2b Phase 3 実装時に判明したこと（2026-07-26）

**カクヨムのジャンル enum は表示名から推測できない。** サイトの JS バンドルから取得した
一次情報が次のとおりで、`ACTION` は「アクション」ではなく**現代ファンタジー**、
`ROMANCE` は「恋愛」ではなく**ラブコメ**（「恋愛」は `LOVE_STORY`）。全14件。

```
FANTASY=異世界ファンタジー  ACTION=現代ファンタジー  SF=SF  LOVE_STORY=恋愛
ROMANCE=ラブコメ  DRAMA=現代ドラマ  HORROR=ホラー  MYSTERY=ミステリー
NONFICTION=エッセイ・ノンフィクション  HISTORY=歴史・時代・伝奇  CRITICISM=創作論・評論
OTHERS=詩・童話・その他  MAHO=魔法のiらんど  FAN_FICTION=二次創作
```

なろうは公式 API ドキュメントのコード表（小ジャンル21件・大ジャンル7件）を採用した。

**アルファポリスはページ全体を検索してはいけない（実装中に取り違えを検出）。** 作品ページには
推薦カードが数十件並んでおり、`c-attribute-tag` はページ内に **57回**、`文字数` は **9回**出現する。
当初ページ全体を対象にしたところ、**別作品の R15 と文字数を拾っていた**（作品1の実際の文字数は
611,788 だが、推薦カードの 457,203 を抽出していた）。次のように限定する。

| 項目 | 限定先 |
|---|---|
| タグ | `div.p-content-info` 内の `tag_ids=` リンク |
| 公開日・更新日・文字数・完結判定 | `div.p-sidebar-content-info__detail`（作品本体の値が入る唯一の場所） |
| ジャンル | JSON-LD の `Article.genre`（ページ単位なので安全） |

完結判定は**タグの「完結」ではなく「初回完結日時」欄の有無**で行う。タグが付いていない完結作品が
実在した（テスト作品2は完結だがタグなし）。年齢制限は本体スコープで確認できなかったため出力しない。

**`parse_aozora_text` のヘッダー走査が先頭60行に限定されていた（既存バグ）。** あらすじが長い作品
（実測: なろうの1作で区切り線が64行目・74行目）でヘッダー範囲を確定できず、**ヘッダー全体が余分な
1話として本文に混入**していた（`--from-file` で話数が2→3になる）。上限を `_HEADER_MAX_LINES = 400`
に引き上げ、`_header_slice()` と走査範囲を揃えた。

### 10.3 Phase 4: OPF 出力

`_make_opf()` `:1581` の metadata ブロックを組み立て直す。**`prefix` 宣言を `<package>` に追加**:

```xml
<package … prefix="nd: https://github.com/ayati/novel_downloader/ns#">
```

出力順は現行を保ち、末尾に追加していく（差分を読みやすくするため）。

**検証手段が無い（要準備）**: この環境に **epubcheck は未インストール**。`java` はある
（`/usr/bin/java`）ので、`epubcheck.jar` を落とすか `pip install epubcheck`（jar 同梱の
ラッパ）で用意する。**Phase 4 は epubcheck を通すまで完了としない**。特に事故りやすいのは:

- `refines="#id"` の参照先 id が manifest/metadata に実在するか（RSC-005）
- `dc:title` を複数出すときの `title-type` 指定漏れ
- 未宣言プレフィックスの `property`（OPF-027 系）

**しおり互換（確認済み・条件付きで安全）**

yomikake は `makeBookKey('epub_pos_' + title + '__' + creator)` でしおりキーを作る（`:7696`）。
`title` の取得は次のとおりで、**PC版 `:2768` と iOS版 `:3086` の両方が同じ実装**:

```js
const titleEl = opfDoc.querySelector('metadata > *|title, metadata > title');
```

`querySelector` は **文書順で最初の1件**を返すだけで、`title-type` は一切見ていない。したがって:

- **本題の `<dc:title>` を必ず先頭に出力する限り、subtitle を足しても bookKey は変わらない＝しおりは割れない。**
- 逆に **subtitle を先に出力すると全書籍のしおりが割れる**。`_make_opf()` の出力順は
  「main → subtitle」で固定し、**この順序を変えないことをコメントで明示**する。

また yomikake は subtitle の存在を知らないため、キャッチコピーは**表示されない**（無害に無視される）。
書誌ブロックに出すには `title-type="subtitle"` を読む改修が要る → Phase 5 の作業とする。

`dc:creator` は `metadata > *|creator` を**全件** join するので、`dc:contributor` を足すのは安全
（§8 のとおり、`dc:creator` 自体を変えなければよい）。

### 10.4 版数

現在 `__version__ = "2.3.1"`（`:94`）。Phase 2 は内部構造の変更で外から見た挙動が
ほぼ変わらないため `2.4.0`、Phase 3・4 で機能が見えるので `2.5.0` を想定。
リリースは `scripts/release.sh <X.Y.Z> --notes-file …` に一本化（手で `__version__` を触らない）。
