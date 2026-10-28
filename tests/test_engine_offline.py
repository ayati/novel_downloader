# -*- coding: utf-8 -*-
"""エンジン（novel_downloader.py）のオフライン単体テスト。

ネットワークにも画面にも触れないものだけ。ここが落ちたら GUI 側を見る前に
まずこちらを直す。
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, make_work_txt  # noqa: E402
import novel_downloader as N  # noqa: E402


def main() -> int:
    ck = Checker("エンジン（オフライン）")

    # ── 短縮URL展開のリダイレクト先検査（design_gui_v2 §8.11）──
    for u in ("http://127.0.0.1/x", "http://localhost/x", "http://192.168.1.1/admin",
              "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data/",
              "http://[::1]/", "http://100.64.0.1/", "http://172.16.0.1/"):
        ck(f"内部アドレスを追わない: {u}", N._is_public_http_url(u) is False)
    for u in ("file:///etc/passwd", "gopher://x/", "ftp://example.com/"):
        ck(f"http(s) 以外を追わない: {u}", N._is_public_http_url(u) is False)
    for u in ("https://ncode.syosetu.com/n0022gd/", "https://share.google/abc"):
        ck(f"公開ホストは通す: {u}", N._is_public_http_url(u) is True)
    ck("名前解決できないホストは通す（DNS 障害で正当URLを弾かない）",
       N._is_public_http_url("https://no-such-host-xyzzy.example/") is True)
    ck("リダイレクトハンドラが opener に載っている",
       any(isinstance(h, N._NoInternalRedirect)
           for h in N._short_url_opener().handlers))

    # ── 短縮URL判定（オフライン・ホスト名だけ）──
    ck("share.google は短縮URL", N.is_short_url("https://share.google/abc") is True)
    ck("なろうは短縮URLでない",
       N.is_short_url("https://ncode.syosetu.com/n0022gd/") is False)
    ck("サブドメイン偽装に引っかからない",
       N.is_short_url("https://share.google.evil.example/x") is False)

    # ── 失敗の文言（design_gui_v2 §8.12 (5)）──
    f = N._friendly_error
    ck("404 は作品が見つからない扱い",
       "404" in f(N.HTTPError("http://x/", 404, "Not Found", {}, None)))
    ck("403 はアクセス拒否",
       "拒否" in f(N.HTTPError("http://x/", 403, "Forbidden", {}, None)))
    ck("接続断は通信エラー", "通信が切断" in f(ConnectionResetError("reset")))
    ck("タイムアウトも通信エラー", "通信が切断" in f(TimeoutError("timed out")))
    ck("純粋なファイルI/Oはファイル文言",
       "ファイルの読み書き" in f(IsADirectoryError("is a dir")))
    ck("すべて『エラー: 』で始まる（GUI が拾う契約）",
       all(f(e).startswith("エラー: ") for e in
           (ConnectionResetError("x"), TimeoutError("x"), IsADirectoryError("x"),
            RuntimeError("x"), N.URLError("x"))))

    # ── サポートを終えたサイト（ノベルアップ＋・v2.18.0〜）──
    nu = "https://novelup.plus/story/805623797"
    ck("ノベルアップ＋は判定はする（未対応と区別するため）",
       N.detect_site(nu) == "novelup")
    ck("ダウンロード対象からは外れている", "novelup" not in N._SITE_DISPATCH)
    msg = N._retired_site_message("novelup")
    ck("案内は『エラー: 』で始まる（GUI が拾う契約）", msg.startswith("エラー: "), msg)
    ck("案内は終了と理由を伝える",
       "サポートを終了" in msg and "CAPTCHA" in msg and "ブラウザ" in msg, msg)
    ck("手元の .txt から作り直すときの表紙色は残す",
       N._SITE_COLOR_BY_LABEL.get("ノベルアップ＋") == "#0CBF97")
    # --detect-site は stdout.buffer に直接書くので、GUI と同じくサブプロセスで呼ぶ
    out = subprocess.run([sys.executable, N.__file__, "--detect-site", nu],
                         capture_output=True, text=True, encoding="utf-8").stdout
    info = json.loads(out.strip().splitlines()[-1])
    ck("--detect-site: site は null（取得させない）", info["site"] is None)
    ck("--detect-site: retired と表示名を返す",
       info["retired"] is True and info["display_name"] == "ノベルアップ＋", str(info))
    err = io.StringIO()
    code = None
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            N._main([nu])
        except SystemExit as e:
            code = e.code
    ck("URL を渡すと終了コード 1", code == 1, str(code))
    ck("URL を渡すと stderr にサポート終了の案内", "サポートを終了" in err.getvalue(),
       err.getvalue())
    with tempfile.TemporaryDirectory() as d:
        p = make_work_txt(d, "nu.txt", "作品N", "n0001aa", episodes=2)
        with open(p, encoding="utf-8") as fp:
            body = fp.read()
        with open(p, "w", encoding="utf-8") as fp:
            fp.write(body.replace("https://ncode.syosetu.com/n0001aa/", nu))
        with contextlib.redirect_stdout(io.StringIO()):
            r = N._check_update_one(p, 0)
        ck("一括確認はサポート終了を理由に通信せず止まる",
           "サポートを終了" in (r.get("error") or ""), str(r))
        rows = N.shelf_scan(d)
        ck("本棚には配信元を出すが site は null",
           rows and rows[0]["display_name"] == "ノベルアップ＋" and rows[0]["site"] is None,
           str(rows))

    # ── なろうの短編判定（design_gui_v2 §8.14 の前提）──
    ck("本文があれば短編とみなす",
       N.narou_looks_like_tanpen('<div class="p-novel__text">本文</div>') is True)
    ck("本文が無ければ短編とみなさない（構造変化と区別する）",
       N.narou_looks_like_tanpen("<html><body>目次だけ</body></html>") is False)

    # ── shelf-scan（オフライン）──
    with tempfile.TemporaryDirectory() as d:
        make_work_txt(d, "A.txt", "作品A", "n0001aa", episodes=3)
        with open(os.path.join(d, "memo.txt"), "w", encoding="utf-8") as fp:
            fp.write("底本URL の無いただのメモ\n")
        rows = N.shelf_scan(d)
        ck("2 件返る（URL の無い .txt も行として返す）", len(rows) == 2, str(len(rows)))
        work = [r for r in rows if r["url"]]
        ck("底本URL を持つのは 1 件", len(work) == 1)
        if work:
            w = work[0]
            ck("題名が読める", w["title"] == "作品A", w["title"])
            ck("話数は手元の数", w["episodes"] == 3, str(w["episodes"]))
            ck("サイトを判定できる", w["display_name"] == "小説家になろう")
            ck("path は絶対パス", os.path.isabs(w["path"]))
        ck("壊れたディレクトリでも落ちない", N.shelf_scan("/no/such/dir") == [])

    # ── 青空文庫は ZIP 原文の書式なのでサイト側と同じ物差しで数える ──
    # 以前は _load_existing_txt（は大見出し の節を数える）で数えていたため、
    # 見出しの無い作品が 0 話・中見出しの作品が 1 話になり「新着あり」に化けた
    sep = "-" * 55
    card = "https://www.aozora.gr.jp/cards/000001/card1.html"
    head = f"題名\n著者\n\n底本URL：{card}\n配信元：青空文庫\n\n{sep}\n記号の説明\n{sep}\n\n"
    tail = "\n\n底本：「全集」出版社\n入力：誰か\n"
    chap = "".join(f"\n［＃５字下げ］{n}［＃「{n}」は中見出し］\n\n本文{n}。\n"
                   for n in ("一", "二", "三"))
    for name, body, want in (("見出しなし", "　本文だけの短い作品。\n", 1),
                             ("中見出し3つ", chap, 3)):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.txt")
            with open(p, "w", encoding="utf-8") as fp:
                fp.write(head + body + tail)
            ck(f"青空文庫（{name}）: 本棚の話数がサイト側と一致",
               N.shelf_scan(d)[0]["episodes"] == want, str(N.shelf_scan(d)[0]["episodes"]))

            def fake_runner(args, _p=p):
                with open(_p, encoding="utf-8") as fp:
                    eps = N.aozora_text_to_episodes(fp.read())[2]
                N._show_episode_list("題名", "著者", [e["title"] for e in eps])
            saved = N._SITE_DISPATCH["aozora"]
            N._SITE_DISPATCH["aozora"] = (saved[0], saved[1], fake_runner)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = N._check_update_one(p, 0)
            finally:
                N._SITE_DISPATCH["aozora"] = saved
            ck(f"青空文庫（{name}）: 新着チェックで新着ありにならない",
               r["status"] == "uptodate" and r["new"] == 0 and r["existing"] == want, str(r))

    # ── 手元の話一覧（§8.15）──
    with tempfile.TemporaryDirectory() as d:
        path = make_work_txt(d, "A.txt", "作品A", "n0001aa", episodes=3)
        rows = N.shelf_scan(d)
        ck("shelf-scan が最後の話の題を返す",
           rows[0].get("last_title") == "第3話", str(rows[0].get("last_title")))

        buf = io.StringIO()
        old_out = N._EVENT_OUT
        N._EVENT_OUT = buf
        try:
            # 人間向けの一覧は stdout に出るので、テストの表示に混ぜない
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    N._show_episode_list("作品A", "著者名", ["第1話", "第2話", "第3話"])
                except SystemExit:
                    pass
        finally:
            N._EVENT_OUT = old_out
        ev = [json.loads(l) for l in buf.getvalue().splitlines() if l.strip()]
        ep = [e for e in ev if e.get("event") == "episodes"]
        ck("episodes イベントが出る", len(ep) == 1)
        if ep:
            ck("題名の配列が載る", ep[0]["titles"] == ["第1話", "第2話", "第3話"])
            ck("題名・著者・件数も載る",
               ep[0]["title"] == "作品A" and ep[0]["author"] == "著者名"
               and ep[0]["total"] == 3)
        ck("送出先を元に戻している（--progress-json 無しでは黙る）",
           N._EVENT_OUT is None)
        ck("フィクスチャは .txt だけで ePub を作っていない",
           [f for f in os.listdir(d) if f.endswith(".epub")] == [])
        ck("_load_existing_txt と話数が一致する",
           len(N._load_existing_txt(path)[1]) == 3)

    # ── 一括チェックの並び順（§8.17）──
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        # 手元の話数（第5引数）と meta の episode_count を**わざと逆にする**。
        # 話数順は手元の数で並ぶべきで、meta で並べていたら逆順になる（§8.19）
        make_work_txt(d, "a.txt", "A", "n0001aa", 1,
                      {"updated": "2020-01-01", "episode_count": 500})
        make_work_txt(d, "b.txt", "B", "n0002bb", 3,
                      {"updated": "2026-09-20", "episode_count": 100})
        make_work_txt(d, "c.txt", "C", "n0003cc", 5,
                      {"updated": "2024-05-05", "episode_count": 10})
        files = sorted(Path(d).glob("*.txt"))
        for mode, exp in (("name", ["a.txt", "b.txt", "c.txt"]),
                          ("updated", ["b.txt", "c.txt", "a.txt"]),
                          ("episodes", ["c.txt", "b.txt", "a.txt"])):
            got = [q.name for q in N._order_txt_files(list(files), mode)]
            ck(f"確認順 {mode}", got == exp, str(got))
        ck("知らない並び順は元のまま",
           [q.name for q in N._order_txt_files(list(files), "zzz")]
           == [q.name for q in files])
        ck("話数順は手元の節数で並べる（meta の総話数だと逆順になる）",
           [q.name for q in N._order_txt_files(list(files), "episodes")]
           == ["c.txt", "b.txt", "a.txt"])

    # 更新日が無いファイルは mtime で代用する（§8.19）
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        import time as _t
        old_p = make_work_txt(d, "old.txt", "古い", "n0001aa", 1)
        _t.sleep(1.1)
        new_p = make_work_txt(d, "new.txt", "新しい", "n0002bb", 1)
        dated = make_work_txt(d, "dated.txt", "日付あり", "n0003cc", 1,
                              {"updated": "2035-01-01"})
        got = [q.name for q in N._order_txt_files(sorted(Path(d).glob("*.txt")),
                                                  "updated")]
        ck("更新日を持つものが先頭", got[0] == "dated.txt", str(got))
        ck("更新日が無くても mtime で新しい方が先",
           got.index("new.txt") < got.index("old.txt"), str(got))
        ck("更新日と mtime を同じ尺度で比べている",
           N._txt_recency(dated) > N._txt_recency(new_p) > N._txt_recency(old_p))

    # ── 一覧の行番号を --start に渡せるサイトか（§8.19）──
    for site in ("narou", "kakuyomu", "alphapolis", "hameln", "monogatary",
                 "sutekibungei", "days", "solispia", "novema",
                 "neopage", "noichigo", "berrys"):
        ck(f"行番号を渡せる: {site}", N.start_from_list_ok(site) is True)
    for site in ("estar", "genpaku", "hyuki", "aozora"):
        ck(f"行番号を渡せない: {site}", N.start_from_list_ok(site) is False)
    ck("未判定のサイトには渡さない", N.start_from_list_ok(None) is False)

    # ── 部分取得の印（§8.19）──
    with tempfile.TemporaryDirectory() as d:
        url = "https://ncode.syosetu.com/n0001aa/"
        meta = {"site": "小説家になろう"}
        N._START_OFFSET = 0
        ck("--start 無しなら印を付けない",
           "開始位置" not in N.aozora_header("作", "者", "", url, meta))
        N._START_OFFSET = 1
        ck("--start 1 は先頭からなので印を付けない",
           "開始位置" not in N.aozora_header("作", "者", "", url, meta))
        N._START_OFFSET = 500
        hdr = N.aozora_header("作", "者", "", url, meta)
        ck("--start 500 で印が付く", "開始位置：500" in hdr)
        path = os.path.join(d, "P.txt")
        N.write_file(path, hdr, [f"{N.aozora_chapter_title('第500話')}\n\n本文\n"],
                     N.aozora_colophon("作", url, "小説家になろう"))
        ck("読み戻せる",
           N._extract_meta_from_txt(path).get("start_offset") == 500)
        ck("shelf-scan からも見える",
           (N.shelf_scan(d)[0].get("meta") or {}).get("start_offset") == 500)
        N._START_OFFSET = 0
        _t, _a, _s2, _e, m2 = N.parse_aozora_text(
            open(path, encoding="utf-8").read())
        ck("--from-file で作り直しても印が消えない",
           "開始位置：500" in N.aozora_header(_t, _a, _s2, url, m2))
        ck("渡された meta を書き換えない（呼び出し側に漏らさない）",
           "start_offset" not in meta)

    # ── checkresult の path は realpath（§8.12 (9)）──
    with tempfile.TemporaryDirectory() as d:
        real = os.path.join(d, "real")
        os.makedirs(real)
        src = make_work_txt(real, "A.txt", "作品A", "n0001aa", episodes=1)
        link = os.path.join(d, "link.txt")
        try:
            os.symlink(src, link)
            buf = io.StringIO()
            old_out = N._EVENT_OUT
            N._EVENT_OUT = buf
            try:
                N._emit_checkresult({"file": "link.txt", "status": "uptodate"}, link)
            finally:
                N._EVENT_OUT = old_out
            ev = json.loads(buf.getvalue().strip())
            ck("symlink の .txt でも shelf_scan と同じ path を出す",
               ev["path"] == os.path.realpath(src), ev["path"])
        except (OSError, NotImplementedError):
            ck.skip("symlink を作れない環境")

    # ── macOS 標準フォントの探索（fc-list が無く Linux/Windows の候補名も当たらない）──
    # Finder 経由のファイル名は NFD のことがあるので、NFD で置いても見つかること
    if N._FONT_BOLD_PATH:
        import unicodedata
        with tempfile.TemporaryDirectory() as td:
            fonts = os.path.join(td, "Fonts")
            asset = os.path.join(td, "Assets", "x.asset", "AssetData")
            os.makedirs(fonts)
            os.makedirs(asset)
            try:
                os.symlink(N._FONT_BOLD_PATH, os.path.join(
                    fonts, unicodedata.normalize("NFD", "ヒラギノ明朝 ProN.ttc")))
                os.symlink(N._FONT_BOLD_PATH, os.path.join(asset, "YuMincho.ttc"))
                got = N._mac_find_cjk_fonts([fonts])[0]
                ck("NFD 名のヒラギノ明朝を見つける",
                   got and got.startswith(fonts), got)
                got = N._mac_find_cjk_fonts([os.path.join(td, "Assets")])[0]
                ck("アセット置き場の游明朝を見つける",
                   got and got.endswith("YuMincho.ttc"), got)
                ck("何も無ければ None",
                   N._mac_find_cjk_fonts([os.path.join(td, "none")])[0] is None)
            except (OSError, NotImplementedError):
                ck.skip("symlink を作れない環境")

    # ── raqm の無い環境でも題簽表紙を JPEG で作る ──
    # Android（Chaquopy）・PyInstaller の exe は raqm を持たない。以前は
    # direction="ttb" が例外になり表紙ごと SVG へ落ちていた。
    if not (N._PILLOW_AVAILABLE and N._FONT_BOLD_PATH):
        ck.skip("Pillow か CJK フォントが無い環境")
    else:
        from PIL import Image, ImageDraw, ImageFont
        orig_font, orig_raqm = N._cover_font, N._has_raqm

        def basic_font(size, bold=True):
            f = orig_font(size, bold)
            return ImageFont.truetype(f.path, size, index=f.index,
                                      layout_engine=ImageFont.Layout.BASIC)
        N._cover_font, N._has_raqm = basic_font, (lambda: False)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                data, fmt = N.make_cover_image(
                    "「ちょっと待って！」……灰色のメーカー～第3章～", "著者",
                    "#16234b", "カクヨム")
            ck("raqm なしでも表紙は JPEG（SVG に落ちない）",
               fmt == "jpg" and data[:2] == b"\xff\xd8", fmt)

            def ink_bbox(ch):
                im = Image.new("L", (100, 100), 0)
                N._draw_vchar_basic(ImageDraw.Draw(im), 0, 0, ch,
                                    basic_font(100), 255)
                return im.getbbox()
            b = ink_bbox("ー")
            ck("長音符は縦棒になる", b and (b[3] - b[1]) > 2 * (b[2] - b[0]), b)
            # 縦組みの鉤括弧は続く文字の側に寄る: 開きは字枠の下、閉じは上
            b = ink_bbox("「")
            ck("開き鉤括弧は字枠の下に寄る（縦組みの字形）", b and b[1] > 50, b)
            b = ink_bbox("」")
            ck("閉じ鉤括弧は字枠の上に寄る（縦組みの字形）", b and b[3] < 50, b)
            b = ink_bbox("っ")
            ck("小書き仮名は字枠の右上に寄る",
               b and (b[0] + b[2]) / 2 > 50 and (b[1] + b[3]) / 2 < 55, b)
            # 縦書き用互換文字（U+FE10〜）を持たないフォントでも豆腐にしない。
            # 同梱の AyatiShowaSerif がそれ（Android の表紙で使う）で、
            # 「エーリカのきらきら【冬の童話祭2026】」の【】が豆腐になった
            ayati = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "font", "AyatiShowaSerif-Regular.ttf")
            if not os.path.exists(ayati):
                ck.skip("font/AyatiShowaSerif-Regular.ttf が無い")
            else:
                af = ImageFont.truetype(ayati, 100,
                                        layout_engine=ImageFont.Layout.BASIC)
                ck("前提: AyatiShowaSerif は ︻ を持たない",
                   N._font_has_glyph(af, "︻") is False)

                def ink_bbox_a(ch):
                    im = Image.new("L", (100, 100), 0)
                    N._draw_vchar_basic(ImageDraw.Draw(im), 0, 0, ch, af, 255)
                    return im.getbbox()
                b = ink_bbox_a("【")
                ck("互換文字の無いフォントでも【は横長に倒れる（豆腐でない）",
                   b and (b[2] - b[0]) > 2 * (b[3] - b[1]), b)
                b = ink_bbox_a("、")
                ck("互換文字の無いフォントでも読点は右上に寄る",
                   b and b[0] > 50 and b[3] < 50, b)
        finally:
            N._cover_font, N._has_raqm = orig_font, orig_raqm

        # ── --cover-font（表紙の題名・著者名のフォントを利用者が選ぶ）──
        saved = (N._FONT_BOLD_PATH, N._FONT_BOLD_IDX,
                 N._FONT_MEDIUM_PATH, N._FONT_MEDIUM_IDX)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ayati = os.path.join(root, "font", "AyatiShowaSerif-Regular.ttf")
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                ng_missing = N._apply_cover_font("/no/such/font.ttf")
                ng_notfont = N._apply_cover_font(os.path.abspath(__file__))
            ck("存在しないファイルは受け付けず自動検出のまま",
               ng_missing is False and N._FONT_BOLD_PATH == saved[0])
            ck("フォントでないファイルも受け付けず自動検出のまま",
               ng_notfont is False and N._FONT_BOLD_PATH == saved[0])
            if os.path.exists(ayati):
                with tempfile.TemporaryDirectory() as d:
                    src = make_work_txt(d, "A.txt", "作品A", "n0001aa", episodes=1)
                    with contextlib.redirect_stdout(io.StringIO()), \
                         contextlib.redirect_stderr(io.StringIO()):
                        try:
                            N.main(["--from-file", src, "--cover-font", ayati,
                                    "--output-dir", d])
                        except SystemExit:
                            pass
                    ck("--cover-font を指定すると表紙はそのフォントで描く",
                       N._FONT_BOLD_PATH == ayati, str(N._FONT_BOLD_PATH))
                    ck("--cover-font 付きでも ePub ができる",
                       any(f.endswith(".epub") for f in os.listdir(d)))
            else:
                ck.skip("font/AyatiShowaSerif-Regular.ttf が無い")
        finally:
            (N._FONT_BOLD_PATH, N._FONT_BOLD_IDX,
             N._FONT_MEDIUM_PATH, N._FONT_MEDIUM_IDX) = saved

    # ── 作者ページの URL（design_author_url.md）──
    au = N._site_url
    ck("相対 URL を作品ページから解決する",
       au("/users/abc", "https://kakuyomu.jp/works/1") == "https://kakuyomu.jp/users/abc")
    ck("../ も解決する",
       au("../../index_pages/person35.html", "https://www.aozora.gr.jp/cards/000035/card1567.html")
       == "https://www.aozora.gr.jp/index_pages/person35.html")
    ck("http は捨てる（https に上げない）", au("http://kakuyomu.jp/users/a", "https://kakuyomu.jp/") == "")
    ck("javascript: は捨てる", au("javascript:alert(1)", "https://kakuyomu.jp/") == "")
    ck("別ホストは捨てる", au("https://evil.example/users/a", "https://kakuyomu.jp/") == "")
    ck("空は空", au("", "https://kakuyomu.jp/") == "" and au(None, "https://kakuyomu.jp/") == "")
    ck("許可ホストを明示すれば別ホストを通す",
       au("https://mypage.syosetu.com/1/", "https://ncode.syosetu.com/",
          N._NAROU_AUTHOR_HOSTS) == "https://mypage.syosetu.com/1/")
    ck("許可ホストを明示したら作品と同じホストでも通さない",
       au("https://ncode.syosetu.com/x/", "https://ncode.syosetu.com/", N._NAROU_AUTHOR_HOSTS) == "")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None
    if BeautifulSoup:
        # おすすめ欄の他作者を拾わない（実測でどのサイトにもある）
        html = ('<div class="subDetails-02"><div class="name">'
                '<a href="https://www.no-ichigo.jp/member/n565522">汐見 夏衛</a></div></div>'
                '<div class="reco"><a href="https://www.no-ichigo.jp/member/n1">他人</a></div>')
        m = N._starts_meta_from_page(BeautifulSoup(html, "html.parser"), "野いちご", "noichigo")
        ck("野いちご系: 著者欄の作者ページ",
           m.get("author_url") == "https://www.no-ichigo.jp/member/n565522")
        html = ('<div class="reco"><a class="c-link" href="https://www.alphapolis.co.jp/author/detail/1">他人</a></div>'
                '<a class="p-content-info__author" href="https://www.alphapolis.co.jp/author/detail/243223524">作者</a>')
        ck("アルファポリス: 著者要素の作者ページ",
           N.alp_get_work_info(BeautifulSoup(html, "html.parser")).get("author_url")
           == "https://www.alphapolis.co.jp/author/detail/243223524")
        # カクヨム: レビュー投稿者の /users/ が先に並ぶ。作品の author 参照から組む
        nd = {"props": {"pageProps": {"__APOLLO_STATE__": {
            "Work:9": {"id": "9", "title": "T", "author": {"__ref": "UserAccount:1"}},
            "UserAccount:1": {"name": "tea_kaijyu", "activityName": "@tea_kaijyu"},
            "UserAccount:2": {"name": "reviewer", "activityName": "評者"}}}}}
        html = '<a href="/users/reviewer">評者</a>'
        ck("カクヨム: Apollo の作者参照から組む",
           N.kky_get_work_info(BeautifulSoup(html, "html.parser"), nd,
                               "https://kakuyomu.jp/works/9").get("author_url")
           == "https://kakuyomu.jp/users/tea_kaijyu")
    else:
        ck.skip("bs4 が無い（作者ページの抽出）")
    html = ('<a href="../../index_pages/person1.html">作家別作品リスト</a>'
            '<tr><td class="header">著者名：</td><td><a href="../../index_pages/person35.html">太宰 治</a></td></tr>'
            '<tr><td class="header">翻訳者名：</td><td><a href="../../index_pages/person9.html">訳者</a></td></tr>')
    ck("青空文庫: 「著者名」の行だけを見る",
       N.aozora_get_work_info(html).get("author_url")
       == "https://www.aozora.gr.jp/index_pages/person35.html")

    with tempfile.TemporaryDirectory() as d:
        url, aurl = "https://ncode.syosetu.com/n0001aa/", "https://mypage.syosetu.com/1/"
        meta = {"site": "小説家になろう", "author_url": aurl}
        hdr = N.aozora_header("作", "者", "", url, meta)
        ck("ヘッダーに作者ページ", f"作者ページ：{aurl}" in hdr)
        col = N.aozora_colophon("作", url, "小説家になろう", author="者", author_url=aurl)
        ck("奥付: 作者ページは底本 URL より後ろ", 0 < col.index(url) < col.index(aurl))
        ck("奥付: 作者ページが無ければ作者行を出さない",
           "作者：" not in N.aozora_colophon("作", url, "小説家になろう", author="者"))
        path = os.path.join(d, "A.txt")
        N.write_file(path, hdr, [f"{N.aozora_chapter_title('第1話')}\n\n本文\n"], col)
        ck("底本 URL は作者ページに化けない", N._extract_url_from_txt(path) == url)
        ck(".txt から読み戻せる", N._extract_meta_from_txt(path).get("author_url") == aurl)
        ck("OPF の nd:authorUrl", ("authorUrl", aurl) in N._nd_meta_pairs(meta))
        x = N._make_colophon_xhtml("作", url, "小説家になろう", author="者", author_url=aurl)
        ck("ePub 奥付: 最初のリンクは底本 URL のまま", N._epub_colophon_to_source(x)[0] == url)
        ck("ePub 奥付に作者ページのリンク", f'href="{aurl}"' in x)

    # ── シリーズでないものを series に入れない（design_author_url.md §5-8）──
    ck("カクヨムのレーベルは label",
       N._kky_meta_from_work({"publicationLabelName": "カドカワBOOKS"}).get("label") == "カドカワBOOKS"
       and "series" not in N._kky_meta_from_work({"publicationLabelName": "カドカワBOOKS"}))
    mm = N._mono_meta_from_story({"theme": "雨の日の約束"}, 1)
    ck("monogatary のお題は prompt", mm.get("prompt") == "雨の日の約束" and "series" not in mm)
    am = N.aozora_get_work_info(
        '<tr><td class="header">作品名：</td><td>走れメロス</td></tr>'
        '<tr><td class="header">底本：</td><td>太宰治全集3</td></tr>')
    ck("青空文庫の底本は base_book", am.get("base_book") == "太宰治全集3" and "series" not in am)
    with tempfile.TemporaryDirectory() as d:
        url = "https://www.aozora.gr.jp/cards/000035/card1567.html"
        meta = {"site": "青空文庫", "label": "L", "prompt": "P", "base_book": "太宰治全集3"}
        path = os.path.join(d, "B.txt")
        N.write_file(path, N.aozora_header("作", "者", "", url, meta),
                     [f"{N.aozora_chapter_title('第1話')}\n\n本文\n"],
                     N.aozora_colophon("作", url, "青空文庫"))
        back = N._extract_meta_from_txt(path)
        ck(".txt から label / prompt / base_book を読み戻せる",
           (back.get("label"), back.get("prompt"), back.get("base_book")) == ("L", "P", "太宰治全集3"))
        ck("「底本書名」行が底本 URL の抽出を乱さない", N._extract_url_from_txt(path) == url)
        ck("OPF では baseBook",
           ("baseBook", "太宰治全集3") in N._nd_meta_pairs(meta))

    # ── なろうのシリーズ（design_author_url.md §9）──
    page = ('<p class="p-novel__series">\n<a href="/s1111i/" class="p-novel__series-link">ラス為&amp;シリーズ</a>\n</p>'
            '<h1 class="p-novel__title">第三部</h1>')
    ck("シリーズ名と URL を取る",
       N._narou_series_from_html(page, "https://ncode.syosetu.com/n5702ja/")
       == ("ラス為&シリーズ", "https://ncode.syosetu.com/s1111i/"))
    ck("シリーズに属さない作品は空",
       N._narou_series_from_html('<h1 class="p-novel__title">t</h1>', "https://ncode.syosetu.com/n1/") == ("", ""))
    ck("シリーズ一覧の形でない URL は捨てる（名前は残す）",
       N._narou_series_from_html('<p class="p-novel__series"><a href="/n0001aa/">x</a></p>',
                                 "https://ncode.syosetu.com/n1/") == ("x", ""))

    def _opf(meta):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.epub")
            with contextlib.redirect_stdout(io.StringIO()):
                N.build_epub(path, "作", "者", "", "https://ncode.syosetu.com/n5702ja/", "小説家になろう",
                             [{"title": "第1話", "body": "本文"}], meta=meta)
            import zipfile
            with zipfile.ZipFile(path) as z:
                return z.read("OEBPS/package.opf").decode("utf-8")
    opf = _opf({"site": "小説家になろう", "series": "ラス為シリーズ",
                "series_url": "https://ncode.syosetu.com/s1111i/"})
    ck("belongs-to-collection を出す（collection-type=series）",
       '<meta property="belongs-to-collection" id="series">ラス為シリーズ</meta>' in opf
       and 'refines="#series" property="collection-type">series<' in opf)
    ck("巻数（group-position）は出さない", "group-position" not in opf)
    ck("series_url の無い本（旧版の .txt の「シリーズ：」）からは出さない",
       "belongs-to-collection" not in _opf({"site": "カクヨム", "series": "カドカワBOOKS"}))

    # ── 本の識別子（design_author_url.md §3-7）──
    ck("同じ底本 URL なら同じ識別子",
       N._book_uuid("https://ncode.syosetu.com/n0001aa/") == N._book_uuid("https://ncode.syosetu.com/n0001aa/"))
    ck("底本 URL が違えば別の識別子",
       N._book_uuid("https://ncode.syosetu.com/n0001aa/") != N._book_uuid("https://ncode.syosetu.com/n0002aa/"))
    bu = N._book_uuid
    ck("書き方の揺れ（末尾 /・http・大文字ホスト・#）は同じ識別子",
       len({bu("https://ncode.syosetu.com/n0001aa/"), bu("https://ncode.syosetu.com/n0001aa"),
            bu("http://NCODE.syosetu.com/n0001aa/"), bu("https://ncode.syosetu.com/n0001aa/#top")}) == 1)
    ck("--start で途中から取った本は別の識別子",
       bu("https://ncode.syosetu.com/n0001aa/", 500) != bu("https://ncode.syosetu.com/n0001aa/"))
    ck("--start 1 は全話と同じ",
       bu("https://ncode.syosetu.com/n0001aa/", 1) == bu("https://ncode.syosetu.com/n0001aa/"))

    # ── 読み戻した値の検査（code-review 指摘）──
    m = N._parse_meta_lines("作者ページ：javascript:alert(1)\nシリーズページ：http://x.example/s1a/\n")
    ck("読み戻し: https 以外の作者ページ・シリーズページは捨てる",
       "author_url" not in m and "series_url" not in m)
    ck("読み戻し: https の作者ページは残す",
       N._parse_meta_lines("作者ページ：https://kakuyomu.jp/users/a\n").get("author_url")
       == "https://kakuyomu.jp/users/a")
    m = N._parse_meta_lines("配信元：カクヨム\nシリーズ：カドカワBOOKS\n")
    ck("旧版の「シリーズ：」（カクヨム）は label へ移す", m.get("label") == "カドカワBOOKS" and "series" not in m)
    m = N._parse_meta_lines("配信元：青空文庫\nシリーズ：太宰治全集3\n")
    ck("旧版の「シリーズ：」（青空文庫）は base_book へ移す", m.get("base_book") == "太宰治全集3" and "series" not in m)
    m = N._parse_meta_lines("配信元：小説家になろう\nシリーズ：S\nシリーズページ：https://ncode.syosetu.com/s1a/\n")
    ck("なろうの本物のシリーズは動かさない", m.get("series") == "S")
    page = '<div class="p-novel__series js-x"><a class="p-novel__series-link" href="/s12345ab/">名</a></div>'
    ck("シリーズ: class が増えても・div でも・桁が違っても取れる",
       N._narou_series_from_html(page, "https://ncode.syosetu.com/n1/")
       == ("名", "https://ncode.syosetu.com/s12345ab/"))
    if BeautifulSoup:
        nd = {"props": {"pageProps": {"__APOLLO_STATE__": {
            "Work:9": {"id": "9", "title": "T", "author": {"__ref": "UserAccount:1"},
                       "alternateAuthorName": "作家"},
            "UserAccount:1": {"name": "label_official", "activityName": "レーベル公式"}}}}}
        ck("カクヨム: 別名義で掲載している作品は作者ページを出さない",
           "author_url" not in N.kky_get_work_info(BeautifulSoup("", "html.parser"), nd,
                                                   "https://kakuyomu.jp/works/9"))

    ck("底本 URL の無い本は毎回別（ローカル由来を同一視しない）",
       N._book_uuid("") != N._book_uuid("") and N._book_uuid("/tmp/a.epub") != N._book_uuid("/tmp/a.epub"))

    # ── normalize_url の quiet・Android の bridge は sys.stdout に触らない ──
    redirect_stdout = contextlib.redirect_stdout
    ep = "https://ncode.syosetu.com/n9623lp/1/"
    buf = io.StringIO()
    with redirect_stdout(buf):
        loud = N.normalize_url(ep, "narou")
    ck("normalize_url: 既定では正規化を知らせる", "[情報]" in buf.getvalue())
    buf = io.StringIO()
    with redirect_stdout(buf):
        q = N.normalize_url(ep, "narou", quiet=True)
    ck("normalize_url: quiet なら何も出さず結果は同じ",
       buf.getvalue() == "" and q == loud == "https://ncode.syosetu.com/n9623lp/", q)

    # bridge は Android 用だが純 Python。ダウンロード中（run が sys.stdout を
    # 差し替えている）に呼ばれても出力先を奪わないことを確かめる。redirect_stdout は
    # 抜けるときに元へ戻すので、前後の sys.stdout を比べても分からない。呼ばれたこと自体を記録する
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "android", "app", "src", "main", "python"))
    sys.modules.setdefault("novel_downloader", N)
    try:
        import bridge
    except Exception as e:
        bridge = None
        ck("bridge を import できる", False, str(e))
    if bridge:
        swaps = []
        real = bridge.contextlib.redirect_stdout

        def spy(target):
            swaps.append(target)
            return real(target)
        bridge.contextlib.redirect_stdout = spy
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                i = bridge.find_work("http://NCODE.syosetu.com/n9623lp/5/#x",
                                     json.dumps(["https://ncode.syosetu.com/n0001aa/",
                                                 "https://ncode.syosetu.com/n9623lp"]))
                d = json.loads(bridge.detect(ep))
        finally:
            bridge.contextlib.redirect_stdout = real
        ck("bridge.find_work: 話の URL・http・大小・# の揺れを越えて同じ作品を見つける", i == 1, str(i))
        ck("bridge.detect: 作品トップへ正規化する",
           d.get("normalized_url") == "https://ncode.syosetu.com/n9623lp/", str(d))
        ck("bridge.find_work / detect: sys.stdout を差し替えない（ダウンロードのログを奪わない）",
           swaps == [], str(swaps))
        ck("bridge.find_work / detect: 何も出力しない", buf.getvalue() == "", repr(buf.getvalue()))

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
