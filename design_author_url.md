# 設計書：作者ページの URL（`nd:authorUrl`）

- 対象: `novel_downloader.py`（第1段）→ `yomikake.html` / `yomikake_ios.html`（第2段）
- 関連: yomikake `design_finished_next.md` §7-2（E）・本リポジトリ `design_metadata_expansion.md`（`nd:*` の仕組み）
- ステータス: **実装済み（2026-10-27・novel_downloader 側）**。yomikake 側も実装済み（2026-10-27・実機確認待ち）
- 調査日: 2026-10-27。各サイトの作品ページを実取得して確認した（ハーメルンは Playwright 経由）

---

## 1. 目的

yomikake の読了パネル「この著者の本」の **🔍 Web で探す**は Google 検索（`"名前" 作品`）しか無い。
Web 小説のペンネームは一般語と衝突しやすく（「n」「れもん」「firework」…）、検索では作者に辿り着けないことが多い。
投稿サイトの**作者ページ**（作品一覧）へ直接飛べれば、「同じ作者の別作品を探す」が 1 タップで済む。

作者ページの URL は**ダウンロード時にしか分からない**（ePub から逆算できない）ので、novel_downloader が書き、yomikake が読む。
**novel_downloader を先に出す**（yomikake 側は値が来ないと何も出ないだけなので、順序が逆でも壊れはしないが、確かめようがない）。

## 2. 各サイトの実測

| サイト | 作者ページ | 取り出し元（既存の著者取得と同じ要素） | 備考 |
|---|---|---|---|
| なろう | `https://mypage.syosetu.com/{userid}/` | **API の `userid`**（`of=` に `u` を足す） | 実測 `userid=1866242` |
| なろう R18 | `https://xmypage.syosetu.com/{xid}/` | 作品情報ページ「作者名」の `<a href>` | **API は `userid` を返さない**（実測）。HTML 経路のときだけ取れる |
| カクヨム | `https://kakuyomu.jp/users/{name}` | `__NEXT_DATA__` の `UserAccount.name` | ⚠ ページ上の最初の `/users/` リンクは**レビュー投稿者**（実測）。必ず Apollo の作者参照から組む |
| アルファポリス | `https://www.alphapolis.co.jp/author/detail/{id}` | `a.p-content-info__author` の href | 下方に他作者のリンクが多数ある |
| エブリスタ | `https://estar.jp/users/{id}` | `a.nickname` の href（相対） | Nuxt の `user` に id もあるはず（未確認） |
| 野いちご / berry's cafe / ノベマ！ | `https://{host}/member/n{id}` | `div.subDetails-02 div.name a` の href | 3 サイト同じ組み（starts 系）。おすすめ欄に他作者の `/member/` が並ぶ |
| ハーメルン | `https://syosetu.org/user/{id}/` | `[itemprop=author] a[itemprop=url]` | 既存の `itemprop=author` 要素の中 |
| ネオページ | `https://my.neopage.com/uid/{uid}` | `book.author.uid` | タイトル「firework の作品一覧」を確認。`www.neopage.com/author/{uid}` は 307（使わない） |
| ステキブンゲイ | `https://sutekibungei.com/users/{name}` | 既存の `a[href^="/users/"]`（相対） | |
| NOVEL DAYS | `https://novel.daysneo.com/author/{name}/` | `div.author a` の href（相対） | 下方に他作者の `/author/` が並ぶ |
| monogatary | `https://monogatary.com/user_page/story/{userId}` | API `/api/story/{id}` の `userId` | SPA のルート表から特定（`USER_PAGE_STORY`）。「○○さんの投稿した物語一覧」を確認 |
| 青空文庫 | `https://www.aozora.gr.jp/index_pages/person{n}.html` | 図書カード「著者名：」セル内の `<a href>`（相対 `../../`） | 作家別作品リスト。翻訳作品は「翻訳者名」もあるが**著者名の行だけ**使う |
| ソリスピア | `https://solispia.com/user/{id}/profile` | `a.main-user-underline` の href | 調査初日はサイト全体が 500。復旧後に実測し追加（「○○のプロフィール」を確認） |
| 杉田玄白 / 結城浩 | — | — | 翻訳者の個人サイト。作者ページの概念が無いので出さない |

### 2-1. 実測で分かった落とし穴

- **「ページ内で最初に見つかった作者らしいリンク」を採ってはいけない。** カクヨム（レビュー欄）・アルファポリス・野いちご系・DAYS（おすすめ欄）は、作品ページに**他人の作者ページへのリンクが多数**ある。どれも**既存コードが著者名を取っている要素そのもの**から href を取る（名前とリンクの持ち主が必ず一致する）。
- 相対 URL が多い（エブリスタ・ステキブンゲイ・DAYS・青空文庫）。`urljoin(作品URL, href)` で絶対化する。

## 3. novel_downloader 側

### 3-1. 出力経路は `_META_FIELDS` 1 行で済む

```python
("author_url",    "作者ページ",     "str"),   # "site" の直後
```

これだけで次がすべて揃う（既存の仕組み・`design_metadata_expansion.md`）:

- OPF: `<meta property="nd:authorUrl">https://…</meta>`（`_nd_meta_pairs` がキャメルケース化）
- .txt ヘッダー: `作者ページ：https://…`
- `--from-file` / `--append`（ヘッダーの読み戻し・`_META_FIELDS` のラベル照合）
- `--from-epub`（OPF の `nd:*` 読み戻し）

ラベルに「タイトル」を含めない（`novel_health_check.py` の正規表現が誤マッチする・§1.5）。

### 3-2. 値の検証 `_author_url(href, work_url, hosts)`

各サイトの取得関数は生の href を渡し、共通関数で次を満たすときだけ `meta["author_url"]` に入れる:

1. `urljoin(work_url, href)` で絶対化
2. スキームが `https`（なろう・青空文庫も https で配信されていることを確認済み。`http` は `https` に上げない＝そのまま捨てる）
3. ホストがそのサイトの**許可ホスト**に入っている（なろう＝`mypage.syosetu.com` / `xmypage.syosetu.com`、ネオページ＝`my.neopage.com`、他は作品と同じホスト）

取れなければ**出さない**（空欄のまま。推測で組み立てない）。許可ホストは `_SITE_META` 側に置き、`_SITE_DISPATCH` のタプルは触らない（§1.6c）。

### 3-3. サイトごとの変更点

| サイト | 変更 |
|---|---|
| なろう | API の `fields` に `u` を追加 → `userid` があれば mypage を組む。HTML 経路（R18・API 失敗時）は `NarouInfoParser` が「作者名」の `<dd>` 内の最初の `<a href>` を覚える |
| カクヨム | `kky_get_work_info` の Apollo 分岐で `apollo[akey].get("name")` |
| アルファポリス / 野いちご系 / ハーメルン / ステキブンゲイ / DAYS / エブリスタ | 著者名を取っている要素（またはその親の `<a>`）の href。野いちご・ノベマ！は著者名を og:title から取っているので、href だけ `div.subDetails-02 div.name a` から取る |
| ネオページ | `_neopage_meta_from_book` で `author.uid` |
| monogatary | ストーリー API の `userId` |
| 青空文庫 | `_cell("著者名")` と同じ行の生 HTML から href |

### 3-4. 表示

- ~~`--dry-run` の出力に出してヘルスチェックで見る~~ → **見送り**。`--dry-run` は作品情報（meta）を表示しない作りで（`_dry_run_exit` は書名・著者・話数だけ）、出すには 16 個の `run_*` を触る必要がある。実サイトでの確認は `--end 1` で 1 話だけ取って .txt / OPF / 奥付を見た（§7）。
- **奥付（colophon）にも載せる**（ePub・.txt とも）。`nd:authorUrl` を読むのは yomikake だけだが、奥付ならどのリーダー（Kobo・KOReader・Apple Books）でも .txt でも見える（当初「載せない」としたのを撤回）。
  - ⚠ **底本 URL の後ろに置く。** `--from-epub` の `_epub_colophon_to_source()` は奥付の**最初の `<a href>`** を底本 URL とみなす。
  - 形は底本行に揃える:
    ```
    底本：「タイトル」カクヨム
    　　　https://kakuyomu.jp/works/…
    作者：○○
    　　　https://kakuyomu.jp/users/…
    ```
  - 作者ページが取れなかった本では作者行ごと出さない（奥付の見た目は従来どおり）。

### 3-5. 既存のファイル

古い ePub / .txt には入っていない。`--append` / `--resume` はヘッダーを毎回作り直す（`design_metadata_expansion.md` §1.3）ので、**次に続きを取ったときに自動で埋まる**。一括で埋め直す機能は作らない。

### 3-6. テスト

`tests/test_engine_offline.py` に:
- `_author_url`: 相対→絶対・許可外ホスト・`http:`・`javascript:`・空
- `_nd_meta_pairs` が `authorUrl` を出す / `_format_meta_lines` → 読み戻しの往復
- 奥付に作者行が出る・底本 URL より後ろ・`_epub_colophon_to_source()` が底本 URL を返し続ける・取れない本では作者行が出ない
- 保存済み HTML 断片（カクヨムの Apollo・野いちごの `subDetails-02`・青空文庫のカード）から**作者本人の** URL が取れ、おすすめ欄の他作者を拾わない

実ネットワークの確認は `test_network.py` / ヘルスチェック側。

### 3-7. 本の識別子を毎回同じ値にする（承認済み・実装済み）

`dc:identifier` は `uuid.uuid4()`（`build_epub`）で**作り直すたびに変わる**。`--append` のたびに Calibre・Kobo・Apple Books が別の本として扱い、本棚で重複する。`uuid.uuid5(uuid.NAMESPACE_URL, 底本URL)` にすれば同じ作品は同じ値になる（底本 URL が無いときは従来どおり uuid4）。yomikake のしおりキーは書名＋著者なので影響しない。

## 4. yomikake 側（両ファイル）

### 4-1. 読み取り

`loadEpub` の `nd:*` 読み取りの隣で
`state.bookAuthorUrl = _safeHttpUrl(_ndMeta(opfDoc, 'authorUrl'))`。
`_safeHttpUrl` は `new URL()` で解釈でき、`protocol` が `https:` / `http:` のときだけ値を返す（`javascript:` 等を落とす）。`closeBook` の state リセットにも足す。
**しおりには保存しない**（D と同じく、しおりの仕様変更を伴うため。読みかけリストの著者バーには出せない）。

### 4-2. 出す場所

| 場所 | 表示 |
|---|---|
| 読了パネル「この著者の本」 | `👤 作者ページ（{サイト名}） ↗` を**先頭**に置き、`🔍 Web で探す ↗` は残す |
| ヘルプの書誌ブロック | 底本リンク（`_helpSourceHtml`）の行に `👤 作者ページ ↗` を並べる |

- **Web 検索は消さない**（作者ページはそのサイトの作品しか無い。書籍化作品や他サイトの作品は検索のほうが見つかる）。
- 共著（著者行が複数）でも出す。作者ページは「この作品を投稿したアカウント」のページで、著者名の割り当てとは独立。
- サイト名は既存の `state.bookSourceSite` を使う。無ければ括弧ごと省く。
- リンクは既存と同じ `target="_blank" rel="noopener"`。パネルは閉じない（§3-4 の既存規則）。
- i18n: `finished.authorPage` / `help.authorPage`（4 言語）。

### 4-3. テスト

`tests/cases/finished-panel.js` の fixture `webnovel.epub`（`make-fixtures.py`）に `nd:authorUrl` を足し:
- パネルとヘルプに作者ページのリンクが出る・href が一致する・Web 検索も残る
- `nd:authorUrl` の無い本（`reflow.epub`）では出ない
- `javascript:` を入れた本では出ない（`_safeHttpUrl`）

## 5. 決定事項（2026-10-27）

1. **読了パネルは Web 検索と並べる**（作者ページが先）。作者ページはそのサイトの作品しか無く、書籍化作品・他サイトの作品は検索のほうが見つかる。
2. **ヘルプの書誌ブロックにも出す**。読了パネルは読み終えたときにしか出ない。
3. ~~ソリスピアは見送り~~ → 同日中に復旧したので実測して追加した。
4. **奥付にも載せる**（§3-4）。
5. ~~シリーズ欄の整理は別の弾~~ → **§8 のとおり今回一緒に直す**（読む側がまだ無く、名前を変えるのがいちばん安い時期のため）。
6. **各話の元 URL は不採用**（.txt の書式が変わる割に、今の用途では効果が小さい）。
7. **本の識別子を固定する（§3-7）は採用**。

## 6. 実装の順

1. novel_downloader: `_author_url` ＋ `_META_FIELDS` ＋ 各サイト（コミットはサイト群ごと）＋ テスト ＋ ヘルスチェック → 実機（実サイト）確認 → リリース
2. yomikake: 読み取り ＋ 読了パネル ＋ ヘルプ ＋ i18n ＋ テスト（両ファイル）→ 実機確認 → リリース

## 7. 実装メモ（novel_downloader・2026-10-27）

- 許可ホストは `_SITE_META` を新設せず、各サイトの呼び出しで渡す（なろう＝`_NAROU_AUTHOR_HOSTS`、ネオページ＝`("my.neopage.com",)`、他は作品と同じホスト）。野いちご系は `_STARTS_BASE`。
- エブリスタは `a.nickname` より Nuxt の `user.userId` を優先した（HTML は描画の都合で変わりやすい）。`a.nickname` はフォールバック。
- 青空文庫の .txt は元テキストの奥付をそのまま使うので、作者行が入るのは .txt ヘッダーと ePub（OPF・奥付）だけ。
- **実サイト確認（`--end 1`）**: なろう・カクヨム・アルファポリス・エブリスタ・野いちご・ノベマ！・berry's cafe・ステキブンゲイ・NOVEL DAYS・ネオページ・monogatary・青空文庫・ハーメルン・ソリスピアの 14 サイトで、.txt ヘッダー・`nd:authorUrl`・奥付の 3 か所に**作者本人の**ページが出ることを確認。杉田玄白は従来どおり何も足されない。`--from-file` / `--from-epub` の往復で作者ページが残り、底本 URL が作者ページに化けないこと、`--append` の前後で `dc:identifier` が変わらないことも確認。

## 8. 「シリーズ」欄の整理（2026-10-27 追加・実装済み）

`meta["series"]` にシリーズでないものが入っていた。いまは誰も読んでいない（yomikake・GUI とも）が、本当のシリーズを EPUB 標準の `belongs-to-collection` に出した時点で、**Calibre・KOReader が全集の巻ごとに別のシリーズを作り、yomikake の「次の巻を選ぶ」が「太宰治全集 4 巻」を探しに行く**。そこで別の欄に分けた。

| サイト | 中身 | 新しい欄（OPF / .txt ラベル） |
|---|---|---|
| カクヨム | 書籍レーベル（`publicationLabelName`） | `label` → `nd:label` / 「レーベル」 |
| monogatary | お題（`theme`） | `prompt` → `nd:prompt` / 「お題」。`theme` は表紙色の `theme_color`・yomikake の配色テーマと紛らわしいので避けた |
| 青空文庫 | 底本の書名（全集名） | `base_book` → `nd:baseBook` / 「底本書名」 |

- **ラベルを「底本」にしないこと** —— 奥付の「底本：」を探す処理（`"\n\n底本："` の検索・`_extract_url_from_txt`）と紛らわしい。
- `series` は本当の作品シリーズ（同じ作品群の何巻目か）のためにとっておく。→ §9 でなろうのシリーズを入れた。
- 既存ファイルの「シリーズ：」行は `--append` でヘッダーが作り直されるときに新しい欄へ移る。`--from-file` で作り直した場合は「シリーズ」のまま残る（読む側が無いので実害なし）。
- 実サイト確認: 青空文庫（走れメロス）で「底本書名：太宰治全集3」/`nd:baseBook`、monogatary で「お題：…」/`nd:prompt`。カクヨムのレーベルは単体テストのみ（手元のサンプル作品にレーベルが無い）。

## 9. なろうのシリーズ（2026-10-27 追加・実装済み）

シリーズのタブ（`/sNNNNx/`）を持つのは調べた範囲でなろうだけなので、なろうだけ対応する（ご本人の判断）。

- **取り出し元は目次ページの `<p class="p-novel__series"><a href="/s1111i/" class="p-novel__series-link">名前</a>`**（`_narou_series_from_html`）。目次の 1 ページ目（短編は本文ページ）は元々取得しているので**追加の通信は無い**。作品情報ページにも「シリーズ」欄があるが見ない。
- 出力: `series`（「シリーズ：」/`nd:series`）＋ `series_url`（「シリーズページ：」/`nd:seriesUrl`）＋ OPF の **`belongs-to-collection`（`collection-type=series`）**。
- **巻数（`group-position`）は出さない。** シリーズページの並びは読む順と限らない（実測: 「黒のシャンタル」シリーズは第三部→第二部→第一部の順。ラス為シリーズは本編→第一部→第二部→第三部→特別話）。yomikake の `_seriesOf` は collection に巻数が無ければ書名の末尾から割り出す。Calibre は巻数なしのシリーズとして並べる。
- ⚠ **`belongs-to-collection` は `series_url` があるときだけ出す。** 旧版の .txt は「シリーズ：」にカクヨムのレーベル・青空文庫の底本書名などを入れていたので、`--from-file` で作り直した本からシリーズを作らない。
- 実サイト確認: n5702ja（ラス為シリーズ）で 3 か所に出る・n0022gd（シリーズなし）では出ない。

## 10. レビューでの補正（2026-10-27・code-review / security-review）

code-review の 10 件を実コードで裏取りし、9 件が実在。8 件を直した。security-review は確信度の高い指摘なし（下の 1 と同じ点を基準未満として報告）。

1. **読み戻した URL を検査し直す**（`_clean_read_meta`）。.txt ヘッダー・ePub の `nd:*` から読んだ `author_url` / `series_url` が https の URL でなければ捨てる。手で書き換えた .txt を `--from-file` すると、奥付のリンクに `javascript:` 等がそのまま入っていた。
2. **識別子の揺れを畳む**: http/https・ホストの大小・末尾の `/`・`#` を揃えてから uuid5 にする。
3. **`--start` で途中から取った本は別の識別子**（`#start=N` を足す）。全話の本と同一視すると、Apple Books 等で片方が本棚から消える。`--end` だけの本は全話と同じ（続きを取れば全話になる）。縦書き・横書きの作り分けは同じ作品なので同じ識別子のまま。
4. **カクヨムの別名義（`alternateAuthorName`）の作品は作者ページを出さない。** 出版社・レーベルのアカウントが作家の作品を載せている場合、アカウントのページは作者のページではない。
5. **エブリスタはページ全体の `a.nickname` へのフォールバックをやめた**（コメント欄の別人を拾いうる）。Nuxt の `userId` だけを使う。
6. **なろうのシリーズの取り出しを緩めた**: class が増えても・`div` でも・シリーズコードの桁が違っても取れる。
7. **旧版の「シリーズ：」を読み戻すときに移す**: 配信元がカクヨム→`label`、monogatary→`prompt`、青空文庫→`base_book`（`series_url` を伴うなろうの本物のシリーズは動かさない）。
8. **基底 URL は各サイトの定数（`_ALP_BASE` 等）を使う**（ドメインが変わったとき片方だけ直す事故を防ぐ）。検査関数は用途に合わせて `_site_url` に改名（作者ページとシリーズページの両方に使う）。

見送り: 「`aozora_colophon` に `meta=` を渡せば 17 か所の `author=… author_url=…` が要らない」— 著者名は `meta` に入っていないので結局引数が 1 つ残り、全呼び出しをもう一度書き換える割に得が小さい。ステキブンゲイのページ全体の最初の `/users/` リンクは既存の著者名取得と同じ要素なので、名前とリンクは必ず同じ人を指す（実測でも作者本人）。
