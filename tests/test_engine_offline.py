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

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
