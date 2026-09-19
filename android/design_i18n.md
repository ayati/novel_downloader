# Android 設計書: UI の英語対応（i18n）

対象: `android/`（Kotlin ＋ リソース）
関連: `android/design_gui.md` / `android/design_history.md` / リポジトリ直下 `CLAUDE.md`「国際化（i18n）方針」
**Python 本体（`novel_downloader.py` / `bridge.py`）の変更は不要。**

---

## 1. 目的と方針

対応17サイトはすべて日本語サイトで、ダウンロードされる本文も必ず日本語である。したがって目的は
「全面英語化」ではなく、**日本語コンテンツを扱いたい非日本語環境のユーザーが画面操作で詰まらないこと**。
リポジトリ直下 `CLAUDE.md`「国際化（i18n）方針」と同じ立場を Android でも採る。

**画面に出る操作要素は英語化し、コンテンツと診断ログは日本語のまま残す。**

## 2. 端末ロケールによる自動選択を採用する

Android 標準の**リソース修飾子**を使う。`res/values/strings.xml`（既定＝日本語）と
`res/values-en/strings.xml`（英語）を置けば、**OS が端末の言語設定に応じて自動的に選ぶ**。
切り替え UI も判定コードも書かない。

### 2.1 CLI で `LANG` を見ない判断と矛盾しない理由

Python CLI では `LANG` / `LC_ALL` によるロケール自動判定を**採らない**と決めている（`CLAUDE.md`）。
一見矛盾するが、シグナルの質が違う。

| | CLI（WSL / Windows） | Android |
|---|---|---|
| 判定材料 | 環境変数 `LANG` | 端末の言語設定 |
| 性質 | **付随的な既定値**。`en_US.UTF-8` は日本語ユーザーでも意図せず持っている | **ユーザーが明示的に設定した端末全体の意思表示** |
| 自動追従したときの体験 | 既存ユーザーの表示が無断で変わる | 全アプリと同じ挙動。追従しない方が異物 |

したがって Android では自動追従が正しい。

### 2.2 既定ロケールは日本語（`values/` = 日本語）

`values/` は**どの修飾子にも一致しなかったときの受け皿**でもある。日本語を既定に置くため、
たとえばフランス語端末では英語ではなく日本語が出る。

> **代替案（不採用）**: `values/` を英語にし `values-ja/` を日本語にすると、未対応ロケールでは英語が出る。
> 一般論としてはこちらが有利だが、本アプリの主対象は日本語話者であり、`CLAUDE.md` の
> 「日本語をデフォルトとして維持する」に揃える方を優先する。第三言語の追加を検討する時点で再考する。

---

## 3. 対象の切り分け

現状のハードコード文字列は XML 12件・Kotlin 54件（計66件）。

| 層 | 内容 | 扱い |
|---|---|---|
| **A: 画面部品** | メニュー、ボタン、hint、空状態、`contentDescription`、画面表題、ダイアログ（タイトル・本文・ボタン）、設定の選択肢、行メニュー、サイトバッジ、Toast | **英語化する** |
| **B: 状態・通知** | `準備中…` / `N / M 話` / `中止しました` / `✅ 完了: …` / `❌ 失敗（詳細ログ参照）` / 通知チャンネル名 / `Python 初期化中…` | **英語化する**。コンテンツではなく画面の一部であり、通知にも出る。A だけだと「Download」を押した直後に「準備中…」が出る中途半端な状態になる |
| **C: ログ・診断** | `[アプリ内エラー] …`（3件） | **日本語のまま**。詳細ログは Python 本体の日本語出力と地続きで、ここだけ英語にすると不揃いになる |

---

## 4. 触ってはいけないもの（保護対象）

| 対象 | 現在地 | 理由 |
|---|---|---|
| **`SUBDIR = "小説ダウンローダー"`** | `DownloadService.kt` / `DownloadHistory.kt` の `const val` | **表示文言ではなく保存先フォルダ名＝パス**。文字列リソース化して `values-en` を与えると、端末言語を変えた瞬間に保存先が分岐し、**履歴の URI も `importFolder()` も壊れる**。Kotlin 定数のまま据え置く |
| `[アプリ内エラー] …` | `DownloadService.kt` | §3 の C 層 |
| Python 本体の出力（詳細ログの中身） | `bridge.py` 経由 | 同上 |
| `applicationId` | `build.gradle.kts` | アプリの同一性。表示名とは無関係 |

> `SUBDIR` は Python 側で `底本URL：` をパースキーとして保護したのと**同じ種類の罠**である
> （文字列に見えるが実体は契約）。リソース化の一括作業でうっかり巻き込まないこと。

---

## 5. `app_name` の英語化

`app_name` を `values-en` で **`Novel EPUB Downloader`** にする。

### 5.1 影響範囲（すべて表示専用）

| 箇所 | 効果 |
|---|---|
| `AndroidManifest.xml` `<application android:label>` | ランチャーのアイコン名、設定→アプリ の表示名 |
| `AndroidManifest.xml` `<intent-filter android:label>` | ブラウザの共有シートに出る項目名 |
| `DownloadService.kt` ×2（`setContentTitle`） | 進捗通知・結果通知のタイトル |

### 5.2 巻き込まないもの

- **`applicationId = "com.ayati.noveldownloader"`** — アプリの同一性はこちら。更新の連続性・署名・
  Developer Verification はすべて applicationId と署名鍵で決まり、表示名は無関係
- **`SUBDIR`** — 別の定数（§4）。`app_name` を変えても保存先は動かない
- 永続データ（`history.json` / SharedPreferences）— 参照していない

日本語端末では従来どおり `小説ダウンローダー` のままなので、既存ユーザーの見え方は変わらない。

---

## 6. 文字列リソース設計

### 6.1 命名規則

`<画面>_<用途>_<識別子>`。複数画面で使うものは `common_` を前置する。

### 6.2 キー一覧（約45件）

**共通**

| キー | ja | en |
|---|---|---|
| `app_name` | 小説ダウンローダー | Novel EPUB Downloader |
| `common_btn_open` | 📖 開く | 📖 Open |
| `common_btn_share` | 📤 共有 | 📤 Share |
| `common_share` | 共有 | Share |
| `common_more` | その他 | More |
| `common_delete` | 削除 | Delete |
| `common_cancel` | キャンセル | Cancel |
| `common_close` | 閉じる | Close |
| `toast_no_epub_reader` | ePubリーダーアプリをインストールしてください | Please install an EPUB reader app |

**メイン画面**

| キー | ja | en |
|---|---|---|
| `main_menu_history` | 履歴 | History |
| `main_menu_settings` | 設定 | Settings |
| `main_url_hint` | 作品ページのURL | Work page URL |
| `main_btn_paste` | 📋 貼り付け | 📋 Paste |
| `main_btn_clear` | ✕ クリア | ✕ Clear |
| `main_btn_download` | ⬇ ダウンロード | ⬇ Download |
| `main_btn_cancel` | ⏸ 中止 | ⏸ Cancel |
| `main_log_show` | ▸ 詳細ログ | ▸ Details |
| `main_log_hide` | ▾ 詳細ログ | ▾ Details |
| `main_recent_heading` | 最近のダウンロード（すべて見る） | Recent download (see all) |
| `main_badge_detect_error` | ⚠ 判定エラー | ⚠ Detection failed |
| `main_badge_hameln` | ⚠ ハーメルンはアプリ版では非対応です | ⚠ Hameln is not supported in the app |
| `main_badge_unknown` | 🔗 サイト未判定（短縮URLなら実行時に展開されます） | 🔗 Site unknown (short URLs are expanded at run time) |
| `main_badge_unsupported` | ⚠ 未対応のURLです | ⚠ Unsupported URL |
| `main_toast_no_clipboard_url` | クリップボードにURLがありません | No URL in the clipboard |
| `main_err_no_write_permission` | 保存権限がないためダウンロードできません | Cannot download without storage permission |

**設定ダイアログ**

| キー | ja | en |
|---|---|---|
| `settings_title` | 設定（次のダウンロードから適用） | Settings (applied from the next download) |
| `settings_horizontal` | 横書きにする | Horizontal writing |
| `settings_kobo` | Kobo用拡張子 (.kepub.epub) | Kobo extension (.kepub.epub) |
| `settings_site_cover` | サイトの表紙画像を使う | Use the site cover image |
| `settings_save_txt` | テキスト (.txt) も保存する | Also save text (.txt) |

**履歴画面**

| キー | ja | en |
|---|---|---|
| `history_title` | ダウンロード履歴 | Download history |
| `history_empty` | まだダウンロード履歴がありません | No downloads yet |
| `history_menu_import` | 保存フォルダを取り込む | Import from the save folder |
| `history_menu_clear` | 履歴をすべて削除 | Clear all history |
| `history_clear_message` | 履歴の一覧だけを消します。ダウンロードしたファイルは削除されません。 | Only the history list is cleared. The downloaded files are not deleted. |
| `history_row_redownload` | もう一度ダウンロード | Download again |
| `history_row_remove` | 履歴から削除 | Remove from history |
| `history_remove_message` | 履歴の行だけを消します。ダウンロードしたファイルは削除されません。 | Only this entry is removed. The downloaded file is not deleted. |
| `history_missing_title` | ファイルが見つかりません | File not found |
| `history_missing_message` | 「%1$s」のファイルは削除されたようです。この履歴を消しますか？ | The file for “%1$s” seems to have been deleted. Remove this entry? |
| `history_missing_remove` | 履歴を消す | Remove entry |
| `history_missing_keep` | 残す | Keep |
| `history_file_missing` | ⚠ ファイルが見つかりません | ⚠ File not found |
| `history_toast_no_url` | この履歴には元のURLが記録されていません | This entry has no source URL |
| `history_toast_nothing_imported` | 取り込めるファイルはありませんでした | No files to import |

**状態・通知（B 層）**

| キー | ja | en |
|---|---|---|
| `notif_channel_name` | ダウンロード | Downloads |
| `status_python_init` | Python 初期化中… | Starting Python… |
| `status_preparing` | 準備中… | Preparing… |
| `status_cancelled` | 中止しました | Cancelled |
| `status_failed` | ❌ 失敗（詳細ログ参照） | ❌ Failed (see details) |
| `status_done` | ✅ 完了: %1$s（ダウンロードフォルダ） | ✅ Done: %1$s (Downloads folder) |

---

## 7. ロケール依存の処理

単純な文字列置換では済まない箇所が3つある。

### 7.1 日付書式（`HistoryActivity.formatDate`）

現状は `SimpleDateFormat(pattern, Locale.JAPAN)` にパターンを直書きしている。
**`Locale.JAPAN` のままでは `values-en` を用意しても意図どおりに出ない。**

- パターンを文字列リソースへ出し、`Locale.getDefault()` を使う

| キー | ja | en |
|---|---|---|
| `history_date_time` | HH:mm | h:mm a |
| `history_date_md` | M月d日 | MMM d |
| `history_date_ymd` | yyyy年M月d日 | MMM d, yyyy |

### 7.2 メタ行の区切り

`" ・ "` は日本語の中黒。英語では `" · "` が自然。→ `history_meta_separator`

### 7.3 複数形（`<plurals>`）

日本語に複数形はないが英語にはある。該当は2つ。

```xml
<!-- values/ -->
<plurals name="episode_count"><item quantity="other">%d話</item></plurals>
<plurals name="imported_count"><item quantity="other">%d 件を取り込みました</item></plurals>
<!-- values-en/ -->
<plurals name="episode_count">
    <item quantity="one">%d episode</item><item quantity="other">%d episodes</item>
</plurals>
<plurals name="imported_count">
    <item quantity="one">Imported %d item</item><item quantity="other">Imported %d items</item>
</plurals>
```

進捗の `%1$d / %2$d 話`（`main_progress_episodes` / 通知側も同じ）は分数表記なので
`plurals` にせず通常の文字列で `%1$d / %2$d episodes` とする。

---

## 8. アプリ別の言語設定（Android 13+）

`res/xml/locales_config.xml` を追加し、`AndroidManifest.xml` の `<application>` に
`android:localeConfig="@xml/locales_config"` を宣言する。

```xml
<locale-config xmlns:android="http://schemas.android.com/apk/res/android">
    <locale android:name="ja" />
    <locale android:name="en" />
</locale-config>
```

これだけで **Android 13 以上では「設定 → アプリ → 言語」でこのアプリだけ言語を固定できる**。
英語端末を使う日本語話者の逃げ道になり、CLI の `--lang` に相当する役割を果たす。

- API 33 未満では何も起きない（端末ロケールへの自動追従のみ。壊れはしない）
- **アプリ内に言語ピッカーは作らない。** `AppCompatDelegate.setApplicationLocales` による
  API 33 未満への後方移植も見送る。OS の設定に委ねるのが Android の流儀であり、
  Windows GUI のトグルとは事情が違う

---

## 9. 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `res/values/strings.xml` | 変更 | 約45キー ＋ `plurals` 2件を追加（日本語） |
| `res/values-en/strings.xml` | 新規 | 同じキーの英語 |
| `res/xml/locales_config.xml` | 新規 | §8 |
| `AndroidManifest.xml` | 変更 | `android:localeConfig` を追加 |
| `res/layout/activity_main.xml` | 変更 | ハードコード文字列を `@string/…` へ |
| `res/layout/activity_history.xml` | 変更 | 同上 |
| `res/layout/item_history.xml` | 変更 | `contentDescription` 2件 |
| `res/menu/main_menu.xml` | 変更 | 2件 |
| `res/menu/history_menu.xml` | 変更 | 2件 |
| `MainActivity.kt` | 変更 | `getString(...)` 化（約18件） |
| `HistoryActivity.kt` | 変更 | `getString(...)` 化 ＋ 日付処理の `Locale.getDefault()` 化（§7.1） |
| `DownloadService.kt` | 変更 | B 層のみ `getString(...)` 化。`[アプリ内エラー]` と `SUBDIR` は据え置き |
| `FileActions.kt` | 変更 | Toast 1件 |
| `DownloadHistory.kt` | **変更しない** | `SUBDIR` のみで、それは保護対象（§4） |

---

## 10. 動作確認

```
1. 端末を日本語のまま → 全画面が現状と一字一句同じであること（退行がないこと）
2. 端末を English に変更 → ランチャー名が Novel EPUB Downloader になる
3. English でメイン画面 → hint・ボタン・⋮メニュー・サイトバッジが英語
4. English で設定ダイアログ → 選択肢4件が英語
5. English でダウンロード実行 → 準備中/進捗/完了/通知が英語（B 層）
6. English で詳細ログを開く → 中身は日本語のまま（C 層。これが期待動作）
7. English で履歴画面 → 表題・空状態・行メニュー・ダイアログが英語
8. English で履歴の日付 → 「Mar 21」「Mar 21, 2026」形式（§7.1）
9. English で1話だけの作品 → 「1 episode」（§7.3 の単数形）
10. 保存先が Download/小説ダウンローダー/ のままであること（§4・最重要）
11. English で取り込み → 日本語時に保存したファイルが正しく取り込まれる（§4 の裏取り）
12. Android 13+ で 設定→アプリ→言語 に項目が出て、日本語に固定できること（§8）
```

**確認項目 10 と 11 が最重要。** ここが崩れると履歴機能ごと壊れる。

### 日英キーの突き合わせ（ビルドでは検出できない）

`values-en` にキーが無いと **ビルドは通り、無言で日本語にフォールバックする**（§11）。
実装後・文言追加後は必ず次を実行する。

```bash
python3 tools/check_android_strings.py
```

未訳キー・孤児キー・書式引数の不一致を報告する。終了コードは `0`=一致 / `1`=不一致 / `2`=設定エラー。

---

## 11. リスク

| リスク | 対策 |
|---|---|
| `SUBDIR` を巻き込んでリソース化してしまう | §4 に明記。確認項目 10・11 で検証。`DownloadHistory.kt` は変更対象外とする |
| 日本語表示が一字でも変わる（退行） | 確認項目 1。`values/` には**現在の文字列をそのまま**移すだけで、文言の改善は行わない |
| `getString` 化の際に書式引数を取り違える | `%1$s` / `%1$d` の位置指定を使い、`values-en` でも同じ番号を使う |
| 英語未訳のキーが残る | Android は未定義キーで**ビルドが通らない**ため、実装時に検出される（`values-en` にキーが無い場合は `values/` へフォールバックするので無言で日本語になる点には注意） |
| 第三言語の端末で日本語が出る | 仕様（§2.2）。必要になれば `values/` を英語にする案を再検討 |
