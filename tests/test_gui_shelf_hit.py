# -*- coding: utf-8 -*-
"""本棚にある作品の URL を受けたとき（design_gui_v2 §8.21）。ネットワーク不要。

URL 欄・受信箱のどちらからでも、取り直さずに本棚のその行へ移って
1 件だけ新着を確認する。エンジンの確認は差し替えて checkresult を注入する。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, gui_app, gui_available, make_memo, make_work_txt  # noqa: E402

URL_A = "https://ncode.syosetu.com/n0001aa/"


def main() -> int:
    ck = Checker("GUI・本棚にある作品の URL")
    avail, why = gui_available()
    if not avail:
        ck.skip(why)
        return ck.done()

    shelf = tempfile.mkdtemp(prefix="ndtest_shelf_")
    inbox = tempfile.mkdtemp(prefix="ndtest_inbox_")
    for i in range(1, 13):                       # 一覧を送る必要があるだけ並べる
        make_work_txt(shelf, f"Z{i:02d}.txt", f"作品Z{i}", f"n9{i:03d}zz", episodes=1)
    path_a = make_work_txt(shelf, "A.txt", "作品A", "n0001aa", episodes=2)
    os.utime(path_a, (1_000_000_000, 1_000_000_000))   # 更新順で一覧の末尾に来るように
    make_memo(inbox, "memo.txt", f"メモ {URL_A}\n")
    try:
        with gui_app(output_dir=shelf, inbox_dir=inbox) as (G, app):
            calls = []

            def fake_worker(d, txt=""):
                calls.append(txt)          # 本物のエンジンは呼ばない
            app._shelf_check_worker = fake_worker

            def type_url(u):
                app.var_url.set(u)
                app._start_detect()
                return app.wait(lambda: app._site_info_url == u and app._shelf_loaded, 90)

            # ── URL 欄：本棚にある作品（書き方の揺れごと）──
            ck("判定が返る", type_url("http://ncode.syosetu.com/N0001AA#top"))
            ck("本棚の作品と一致する（http・大文字・# を畳む）",
               app.wait(lambda: app._shelf_hit is not None, 30))
            ck("バッジに本棚にあると出る", "本棚にあります" in app.lbl_site.cget("text"),
               app.lbl_site.cget("text"))
            ck("メインボタンは『新着を確認』", app.btn_main.cget("text") == app._t("check_one"),
               app.btn_main.cget("text"))

            ck("本棚は閉じている", app._shelf_open is False)
            app._on_main_button()
            app.pump()
            ck("押すと 1 件だけ確認する（.txt を渡す）", calls == [app._shelf_hit["path"]],
               str(calls))
            ck("ダウンロードのキューには積まない", app._jobs == [])
            ck("本棚が開く", app._shelf_open is True)
            ck("その行を強調する", app._shelf_focus == app._shelf_hit["path"])
            i = app._shelf_row_index(app._shelf_focus)
            ck("強調の色が付く",
               i >= 0 and app._shelf_rows[i]["name"].cget("fg_color") != "transparent")
            ck("確認中の表示", app._shelf_rows[i]["state"].cget("text") == app._t("shelf_row_checking"))
            app.pump(0.3)
            ck("対象の行は一覧の後ろの方にある", i >= 10, str(i))
            ck("一覧がその行まで送られる",
               app.frm_shelf_list._parent_canvas.yview()[0] > 0.0,
               str(app.frm_shelf_list._parent_canvas.yview()))

            ck("確認中は一括チェックを始めない", (app._shelf_check_updates(), calls)[1] == [calls[0]])

            # 結果（新着あり）
            p = app._shelf_focus
            app._handle_msg(("checkresult", {
                "event": "checkresult", "path": p, "file": "A.txt", "title": "作品A",
                "author": "著者名", "existing": 2, "total": 5, "new": 3,
                "status": "updated", "error": ""}))
            app._handle_msg(("shelfcheck_done", 0))
            app.pump()
            i = app._shelf_row_index(p)
            ck("新着があれば『続きを取得』を押せる",
               app._shelf_rows[i]["button"].cget("state") == "normal")
            ck("URL 欄の下に結果が出る", "新着 3 話" in app.lbl_site.cget("text"),
               app.lbl_site.cget("text"))
            ck("組み直した後も強調が残る",
               app._shelf_rows[i]["name"].cget("fg_color") != "transparent")
            ck("確認が終われば次を受け付ける", app._shelf_single == "")

            # 失敗（単発の --check-update は失敗すると checkresult を出さない）
            calls.clear()
            app._on_main_button(); app.pump()
            ck("もう一度押せる", len(calls) == 1)
            app._handle_msg(("shelfcheck_done", 1)); app.pump()
            ck("前回の新着を残さず失敗として出す",
               (app._shelf_new.get(p) or {}).get("status") == "error")
            ck("失敗の文言", "確認できませんでした" in app.lbl_site.cget("text"))
            ck("失敗なら『続きを取得』は押せない",
               app._shelf_rows[app._shelf_row_index(p)]["button"].cget("state") == "disabled")

            # 実行中は確認しない
            calls.clear()
            app._proc = "x"
            app._shelf_focus_check(app._shelf_hit)
            app._proc = None
            ck("ダウンロード中は確認を始めない", calls == [] and app._shelf_single == "")

            # 閉じたら強調を外す
            app._toggle_shelf(); app.pump()
            ck("本棚を閉じると強調を外す", app._shelf_focus == "")

            # ── 本棚に無い作品は従来どおり ──
            ck("判定が返る（別作品）", type_url("https://ncode.syosetu.com/n7777xx/"))
            app.pump()
            ck("本棚に無ければ一致しない", app._shelf_hit is None)
            ck("メインボタンは『ダウンロード』", app.btn_main.cget("text") == app._t("download"))

            # ── 本棚に後から入った（未走査だった）作品 ──
            app.var_url.set("")
            app.pump()
            ck("空欄では『新着を確認』にしない", app.btn_main.cget("text") != app._t("check_one"))

            # ── 受信箱：取得済みの行から ──
            app._toggle_inbox()
            app._inbox_reload()
            ck("受信箱の走査が終わる",
               app.wait(lambda: not app._inbox_scanning and app._inbox
                        and not any(it["checking"] for it in app._inbox), 120))
            rows = [r for r in app._inbox_rows if r["row"]["have"]]
            ck("取得済みの行がある", len(rows) == 1)
            b = rows[0]["list"]
            ck("取得済みの行のボタンは押せる『🔄』",
               b.cget("text") == "🔄" and b.cget("state") == "normal")
            calls.clear()
            b.cget("command")()
            app.pump()
            ck("受信箱から押すと本棚のその作品を確認する",
               calls == [os.path.realpath(path_a)] or calls == [app._shelf_focus], str(calls))
            ck("本棚が開いて強調", app._shelf_open and app._shelf_focus != "")
            app._handle_msg(("checkresult", {
                "event": "checkresult", "path": app._shelf_focus, "file": "A.txt",
                "title": "作品A", "author": "著者名", "existing": 2, "total": 2,
                "new": 0, "status": "uptodate", "error": ""}))
            app._handle_msg(("shelfcheck_done", 0)); app.pump()
            ck("受信箱の欄に結果が出る", "新着はありません" in app.lbl_inbox_status.cget("text"),
               app.lbl_inbox_status.cget("text"))
            ck("確認を済ませたメモは受信箱から消える",
               not any(it["file"] == "memo.txt" for it in app._inbox))
            ck("done へ移る",
               app.wait(lambda: os.path.exists(os.path.join(inbox, "done", "memo.txt")), 10))

            # 本棚に見つからない（一覧が古い）
            app._inbox_check_have({"path": "x", "url": "https://ncode.syosetu.com/n5555qq/",
                                   "resolved": "", "site_info": {}})
            ck("本棚に無ければ案内を出す",
               app.lbl_inbox_status.cget("text") == app._t("inbox_not_on_shelf"))
    finally:
        import shutil
        shutil.rmtree(shelf, ignore_errors=True)
        shutil.rmtree(inbox, ignore_errors=True)
    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
