# tests/

エンジン（`novel_downloader.py`）と GUI（`novel_downloader_gui.py`）の回帰テスト。

```bash
python3 tests/run_all.py                     # オフラインのみ（既定・十数秒）
NOVEL_TEST_NETWORK=1 python3 tests/run_all.py   # 実サイトに当てるものも含める
python3 tests/run_all.py gui                 # 名前に gui を含むスイートだけ
python3 tests/test_gui_shelf.py              # 1 スイートだけ直接
```

終了コードは `0`=全成功 / `1`=1 件以上失敗 / `2`=該当なし。

## 構成

| ファイル | 対象 | 画面 | 通信 |
|---|---|---|---|
| `test_engine_offline.py` | 短縮URLの転送先検査・失敗文言・短編判定・`--shelf-scan` | 不要 | 不要 |
| `test_gui_pure.py` | URL の畳み込み・Webhook 設定の整形・受信箱のファイル読み・パネル高さ配分 | 不要 | 不要 |
| `test_gui_webhook.py` | Webhook 設定の画面操作 | **要** | 不要 |
| `test_gui_shelf.py` | 本棚の一覧・表示更新・二重起動の防止 | **要** | 不要 |
| `test_gui_inbox.py` | 受信箱の走査・重複判定・`done` への移動 | **要** | 不要 |
| `test_network.py` | 実サイトでの取得（既定でスキップ） | 不要 | **要** |

画面が要るスイートは、`DISPLAY` が無い／`customtkinter` が入っていない環境では
**スキップして成功扱い**にする（`helpers.gui_available()`）。

## 書くときの約束

- **外部ライブラリを増やさない。** pytest 等は使わず、`helpers.Checker` で
  全項目を最後まで走らせて集計する。1 件目で止まると、実機での確認と
  突き合わせるときに「他も壊れているのか」が分からない
- **UI は「ウィジェットを操作して画面がどうなるか」で書く。**
  関数を呼んで戻り値を見る書き方だと、実機で踏んだ
  「チェックが入らない・URL を貼れない」詰み（design_gui_v2.md §8.13a）を
  取り逃す。実際に取り逃した
- **期待値に実装の挙動を書き写さない。** 上の詰みは、テスト側が
  「宛先が空ならチェックが外れる」を期待値にしていたため緑のまま通っていた。
  「利用者が何をしたくて、その結果どうなってほしいか」で書く
- **フィクスチャはエンジン自身の関数で作る**（`helpers.make_work_txt`）。
  青空文庫書式をテスト側に書き写すと、本体が書式を変えたときテストだけ
  古い形を作り続ける
- **GUI テストでは完了時のフォルダ自動オープンを切る**（`helpers.gui_app` が
  やっている）。`_open_folder()` は `subprocess.run()` をタイムアウト無しで
  呼ぶため、WSL では `xdg-open` がブラウザを起こして戻ってこない
- 設定ファイルは一時ディレクトリへ隔離する（`helpers.gui_app`）。
  実ユーザーの `settings.json` を壊さない

## これで拾えないもの

- **実機 Windows の見た目**（DPI スケーリング・フォントの豆腐・SmartScreen）。
  `design_gui_v2.md` の確認項目を人が見る
- **サイト構造の変化**。`novel_health_check.py` が担当（全 18 サイトを `--dry-run`）
- **ePub の仕様適合**。`epubcheck` を通す（CLAUDE.md「動作確認」）
