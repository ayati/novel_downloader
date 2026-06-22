# 本体追加機能 設計書: `--detect-site` / `--list-sites`

> GUI v1（`gui_v1_design.md` §7）のための、本体（`novel_downloader.py`）側読み取り専用モード2つの
> 概要設計・詳細設計。コードを実査したうえで「確実に実装できる」粒度で記述する。

最終更新: 2026-06-23
対象ファイル: `novel_downloader.py`（単一ファイル）

---

## 1. 概要設計

### 1.1 目的
GUI が「サイト判定の正＝本体ひとつ」に集約するための、本体側の読み取り専用 CLI モードを2つ追加する（GUI 設計 §7）。
- **`--detect-site URL`**: URL のサイト種別を判定し、JSON 1行で出力して終了。GUI のクリップボード自動入力・DL前チェック・ハーメルン早期ブロックに使う。
- **`--list-sites`**: 対応サイト一覧を JSON 配列で出力して終了。GUI の［対応サイトを見る］に使う。

### 1.2 設計原則
1. **読み取り専用・オフライン・即時**: ネットワークアクセスをしない。`detect_site()` / `normalize_url()` / `_SITE_DISPATCH` のみを使う。
2. **短縮URLは展開しない**（GUI §7.1）。`expand_short_url()` を呼ばない（ネットワークを使わないため）。
3. **stdout には JSON だけを出す**: GUI は出力を JSON としてパースする。`normalize_url()` が話数URL正規化時に出す `[情報]…` の print を**混入させない**（→ 詳細設計 2.3）。
4. **既存挙動は無改変**: 追加は argparse 2行 ＋ `main()` 早期分岐2ブロックのみ。既存関数には一切手を入れない。
5. **堅牢**: 解析不能でも例外で落とさず `site=null` を返す。

### 1.3 影響範囲（差分の全量）
| 変更 | 箇所 | 規模 |
|---|---|---|
| argparse に2引数追加 | `main()` の `add_argument` 群（〜9376 付近） | 2行 |
| 早期分岐2ブロック追加 | `main()` の `args = parser.parse_args()`（9379）直後 | 約25行 |
| 既存関数の改変 | なし | 0 |

新規 import は不要（`json` / `io` / `contextlib` / `sys` はすべて import 済み: 92–102 行）。

---

## 2. 詳細設計

### 2.1 既存コードの実査結果（設計の根拠）
- `detect_site(url) -> str`（8409）: ホスト判定のみ・**ネットワーク不使用**。未対応は `"unknown"` を返す。ハーメルンは `"hameln"`。
- `normalize_url(url, site) -> str`（8450）: 話数URL→作品トップに正規化。**マッチ時のみ `[情報]…` を3行 print**。非マッチ時は `url` をそのまま return（print なし）。
- `_SITE_DISPATCH: dict[str, tuple[str,str,callable]]`（8632）: `{site_id: (表示名, 表紙色, run関数)}`。**挿入順 = 表示順**として利用可能。
- `main()` の早期分岐パターン（9379〜）: `args = parser.parse_args()` の直後に `if getattr(args, "X", None): … sys.exit(...)` を並べる構造。新モードもこの先頭に差し込む。
- 既存の stdout 抑制パターン: `buf = io.StringIO(); with contextlib.redirect_stdout(buf): …`（8982）。これを流用する。

### 2.2 配置
- argparse: 既存 `add_argument` 群の末尾（例: `--watch-auto-default` の直後）に追加。
- 分岐ロジック: **`args = parser.parse_args()`（9379）の直後**、`--watch` 分岐より前に置く。
  （読み取り専用・オフラインで最優先に短絡させる。`--list-sites` は URL 不要。）

### 2.3 出力規律（最重要）
- **stdout には JSON 1行だけ**を出す。`normalize_url()` の `[情報]…` は `contextlib.redirect_stdout(io.StringIO())` で**捨てる**。
- **必ず UTF-8 バイトで書く**: Windows ではコンソール標準エンコーディングが cp932 になり得る。GUI はパイプを UTF-8 で読むため、日本語 `display_name` が化けないよう
  `sys.stdout.buffer.write(json_str.encode("utf-8"))` で**明示的に UTF-8 出力**する（GUI 側も保険で `PYTHONUTF8=1` を付与推奨）。
- `json.dumps(..., ensure_ascii=False)` で日本語をそのまま出す。

### 2.4 `--list-sites` 仕様
- 引数: `action="store_true"`（値なし）。
- 出力: `_SITE_DISPATCH` を挿入順に列挙した JSON 配列（GUI §7.3）。
```json
[ {"site":"narou","display_name":"小説家になろう"},
  {"site":"kakuyomu","display_name":"カクヨム"}, … ]
```
- 終了コード: `0`。

### 2.5 `--detect-site URL` 仕様
- 引数: `metavar="URL"`、値を取る。
- 処理:
  1. `url = args.detect_site`
  2. `site = detect_site(url)`（オフライン）
  3. `site != "unknown"` かつ `_SITE_DISPATCH` にあれば:
     - `display_name = _SITE_DISPATCH[site][0]`
     - `normalized_url = normalize_url(url, site)`（**stdout 抑制下で実行**）
     - `needs_playwright = (site == "hameln")`
  4. それ以外（未対応）は `site=null` のまま。
  5. JSON 1行で出力。
- 出力スキーマ（GUI §7.1 と一致）:
```json
{ "schema": 1,
  "site": "narou",            // 未対応は null
  "display_name": "小説家になろう",  // 未対応は null
  "needs_playwright": false,  // hameln は true
  "normalized_url": "https://ncode.syosetu.com/n0022gd/" }  // 未対応は null
```
- **短縮URLは展開しない**（`expand_short_url` を呼ばない）。
- 例外は握りつぶし `site=null` で返す（堅牢性）。
- 終了コード: `0`（判定の成否に関わらず。未対応も「正常に判定できた」とみなす）。

### 2.6 実装パッチ（そのまま貼れる素案）

**(a) argparse 追加**（`add_argument` 群の末尾）:
```python
parser.add_argument("--detect-site", dest="detect_site", default=None, metavar="URL",
                    help="URLのサイト種別を判定し JSON 1行で出力して終了（GUI用・読み取り専用・オフライン）")
parser.add_argument("--list-sites", dest="list_sites", action="store_true",
                    help="対応サイト一覧を JSON で出力して終了（GUI用・読み取り専用）")
```

**(b) 早期分岐**（`args = parser.parse_args()` の直後・`--watch` の前）:
```python
    # ── --list-sites: 対応サイト一覧（GUI用・読み取り専用・オフライン） ──
    if getattr(args, "list_sites", False):
        sites = [{"site": sid, "display_name": label}
                 for sid, (label, _color, _runner) in _SITE_DISPATCH.items()]
        sys.stdout.buffer.write(
            (json.dumps(sites, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.flush()
        sys.exit(0)

    # ── --detect-site: サイト判定（GUI用・読み取り専用・オフライン・短縮URL展開なし） ──
    if getattr(args, "detect_site", None):
        _url = args.detect_site
        _res = {"schema": 1, "site": None, "display_name": None,
                "needs_playwright": False, "normalized_url": None}
        try:
            _site = detect_site(_url)
            if _site != "unknown" and _site in _SITE_DISPATCH:
                _label = _SITE_DISPATCH[_site][0]
                # normalize_url は話数URLで [情報]… を print するため stdout を抑制
                with contextlib.redirect_stdout(io.StringIO()):
                    _norm = normalize_url(_url, _site)
                _res.update(site=_site, display_name=_label,
                            needs_playwright=(_site == "hameln"),
                            normalized_url=_norm)
        except Exception:
            pass  # 解析不能は site=None のまま返す
        sys.stdout.buffer.write(
            (json.dumps(_res, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.flush()
        sys.exit(0)
```

> 注: ローカル変数に `_` を付けているのは `main()` 内の他変数との衝突回避＆「この分岐限定」の明示。

---

## 3. 動作確認（実装後に必ず実行）

```bash
# 構文チェック
python -m py_compile novel_downloader.py

# 一覧（17サイトが JSON 配列で1行・日本語が化けないこと）
python novel_downloader.py --list-sites

# 対応サイト・話数URL → 正規化され needs_playwright=false（[情報] 行が混入しないこと）
python novel_downloader.py --detect-site "https://ncode.syosetu.com/n0022gd/1/"
#   期待: {"schema":1,"site":"narou","display_name":"小説家になろう",
#          "needs_playwright":false,"normalized_url":"https://ncode.syosetu.com/n0022gd/"}

# ハーメルン → needs_playwright=true
python novel_downloader.py --detect-site "https://syosetu.org/novel/123456/"

# 未対応サイト → site:null
python novel_downloader.py --detect-site "https://example.com/foo"
#   期待: {"schema":1,"site":null,"display_name":null,"needs_playwright":false,"normalized_url":null}

# 出力が厳密に1行 JSON か（行数チェック）
python novel_downloader.py --detect-site "https://kakuyomu.jp/works/1/episodes/2" | wc -l   # → 1
```

検証ポイント:
- `--list-sites` / `--detect-site` のどちらも **stdout が JSON 1行のみ**（`[情報]…` が混ざらない）。
- 話数URLが `normalized_url` で作品トップに正規化される。
- 日本語 `display_name` が化けない（UTF-8 バイト出力）。

---

## 4. GUI 設計との対応

| GUI 設計 | 本設計での担保 |
|---|---|
| §7.1 `--detect-site` スキーマ（schema/site/display_name/needs_playwright/normalized_url） | 2.5 で完全一致 |
| §7.1 短縮URL展開しない | 2.5（`expand_short_url` 不使用） |
| §7.2 `needs_playwright==true`→ハーメルン早期ブロック | `needs_playwright=(site=="hameln")` |
| §7.3 `--list-sites` スキーマ | 2.4 で一致 |
| §7 「本体が正・GUIに判定を持たせない」 | `detect_site`/`_SITE_DISPATCH` を唯一の真実として参照 |

---

## 4.5 実装メモ（実装時に判明した追加修正）
- **モジュール読込時のフォント診断 print を stderr へ移動**（`novel_downloader.py` 1859 / 1861–1869）。
  `_find_cjk_fonts()` の結果を知らせる `[情報] 日本語フォント検出: …` および `[警告] 日本語フォントが…` は
  従来 **stdout** に出ており、`--detect-site` / `--list-sites` の JSON 行に混入していた（`wc -l` が 2 になる）。
  これらは診断メッセージであり **stderr が正しい置き場所**なので `file=sys.stderr` を付与。
  副次効果として、通常ダウンロード時も GUI の stdout 進捗パース（§9）のノイズが減る。
- 実装・検証済み（2026-06-23）。`python3 -m py_compile` OK、全モードで **stdout は JSON 1行のみ**、
  `json.loads` 可能、正規化／`needs_playwright`／未対応 `null` すべて期待どおり。

## 5. 補足: CLAUDE.md 追記の要否
- オプション表（`novel_downloader/CLAUDE.md`）に `--detect-site` / `--list-sites` の2行を追記すると整合する（GUI 専用の読み取り専用モードである旨）。実装時に合わせて更新する。
