# -*- coding: utf-8 -*-
"""エンジン（novel_downloader.py）のオフライン単体テスト。

ネットワークにも画面にも触れないものだけ。ここが落ちたら GUI 側を見る前に
まずこちらを直す。
"""
import contextlib
import io
import json
import os
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
                 "novelup", "sutekibungei", "days", "solispia", "novema",
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

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
