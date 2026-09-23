# -*- coding: utf-8 -*-
"""本棚の一覧・表示更新（design_gui_v2 §8.4 / §8.14）。ネットワーク不要。"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, gui_app, gui_available, make_work_txt  # noqa: E402


def main() -> int:
    ck = Checker("GUI・本棚")
    avail, why = gui_available()
    if not avail:
        ck.skip(why)
        return ck.done()

    shelf = tempfile.mkdtemp(prefix="ndtest_shelf_")
    make_work_txt(shelf, "A.txt", "作品A", "n0001aa", episodes=2)
    try:
        with gui_app(output_dir=shelf, shelf_open=False) as (G, app):
            app._toggle_shelf()
            if not app.wait(lambda: app._shelf_loaded, 90):
                ck("初回走査が返る", False)
                return ck.done()
            ck("初回走査で 1 件", len(app._shelf_works()) == 1)
            ck("話数は手元の数", app._shelf_works()[0]["episodes"] == 2,
               str(app._shelf_works()[0]["episodes"]))
            ck("走査時にフォルダの更新時刻を控える", app._shelf_dir_mtime is not None)
            ck("直後は stale でない", app._shelf_stale() is False)

            # 新着チェック前は「続きを取得」を押せない
            ck("未チェックのうちは『続きを取得』を押せない",
               all(r["button"].cget("state") == "disabled" for r in app._shelf_rows))

            # checkresult を注入（ネットワークを使わない）
            app._shelf_chk_total = 1
            app._handle_msg(("checkresult", {
                "event": "checkresult", "path": app._shelf_works()[0]["path"],
                "file": "A.txt", "title": "作品A", "author": "著者名",
                "existing": 2, "total": 9, "new": 7,
                "status": "updated", "error": ""}))
            app._handle_msg(("shelfcheck_done", 0))
            app.pump()
            ck("新着が行に出る", app._shelf_new_count() == 1)
            ck("新着があれば『続きを取得』を押せる",
               all(r["button"].cget("state") == "normal" for r in app._shelf_rows))
            ck("見出しに新着数が出る", "新着" in app.btn_shelf.cget("text"),
               app.btn_shelf.cget("text"))

            # ── 外からファイルが増えたとき（§8.14）──
            time.sleep(1.1)                       # mtime の粒度を跨ぐ
            make_work_txt(shelf, "B.txt", "作品B", "n0002bb", episodes=3)
            ck("フォルダが変われば stale と判定する", app._shelf_stale() is True)
            app._toggle_shelf(); app.pump()
            app._toggle_shelf()
            ck("閉じて開き直すと一覧が更新される",
               app.wait(lambda: len(app._shelf_works()) == 2, 90))

            # ── 手動更新（§8.14）──
            time.sleep(1.1)
            make_work_txt(shelf, "C.txt", "作品C", "n0003cc", episodes=1)
            ck("押す前は古いまま", len(app._shelf_works()) == 2)
            app.btn_shelf_reload.cget("command")()
            ck("『一覧を更新』で読み直せる",
               app.wait(lambda: len(app._shelf_works()) == 3, 90))
            ck("新着チェックとは別のボタン",
               app.btn_shelf_reload.cget("text") != app.btn_shelf_check.cget("text"))

            # ── ダウンロード完了で印が立つ（§8.14）──
            for kind, status, want in (("download", "done", True),
                                       ("append", "done", True),
                                       ("download", "error", False)):
                app._shelf_dirty = False
                j = app._make_job("https://ncode.syosetu.com/n9/", kind=kind)
                if kind == "append":
                    j["target"] = app._shelf_works()[0]["path"]
                    j["shelf_path"] = j["target"]
                app._jobs = [j]; app._job_i = 0; j["status"] = "running"
                app._job_finished(status)
                app.pump()
                label = f"{kind}/{status} で印が{'立つ' if want else '立たない'}"
                ck(label, (app._shelf_dirty or app._shelf_loaded) if want
                   else app._shelf_dirty is False)

            # ── 話の一覧・ePub を開く（§8.15）──
            row = app._shelf_works()[0]
            ck("最後の話の題が行に届いている", row.get("last_title") == "第2話",
               str(row.get("last_title")))
            r0 = app._shelf_rows[0]
            ck("『一覧』ボタンがある", r0["list"].cget("text") == "☰")
            ck("ePub が無ければ『開く』は押せない",
               r0["open"].cget("state") == "disabled")

            app._shelf_show_episodes(row)
            ck("一覧を読み込める",
               app.wait(lambda: not app._shelf_listing, 90))
            wins = [w for w in app.winfo_children()
                    if w.winfo_class() == "Toplevel"]
            ck("一覧の窓が開く", len(wins) >= 1)
            for w in wins:
                try:
                    w.destroy()
                except Exception:
                    pass

            # 本棚の窓には「ここから取得」を出さない（続きは --append が担う）
            wshelf = app._show_episode_window("作品A", "手元に 3 話",
                                              ["第1話"], source_url=row.get("url", ""))
            app.pump(0.2)
            ck("本棚の窓に『ここから取得』は出さない",
               not hasattr(wshelf, "start_button"))
            ck("元サイトを開くボタンは出す", wshelf.site_button is not None)
            w2 = app._show_episode_window("作品A", "手元に 3 話", ["第1話"])
            app.pump(0.1)
            ck("URL が無ければ出さない", w2.site_button is None)
            w2.destroy()
            wshelf.destroy()

            win = app._show_episode_window("作品A", "手元に 3 話",
                                           ["第1話", "第2話", "第3話"])
            app.pump(0.2)
            box = [c for c in win.winfo_children()
                   if c.winfo_class() == "CTkTextbox" or "Textbox" in type(c).__name__]
            ck("話数ぶんのラベルを並べず 1 枚のテキストで出す", len(box) == 1)
            if box:
                text = box[0].get("1.0", "end")
                ck("番号付きで全話入っている",
                   "1. 第1話" in text and "3. 第3話" in text, text.strip()[:40])
            win.destroy()

            # ── 並び順（表示＝確認順・§8.17）──
            saved_shelf = app._shelf
            # 題名とファイル名の順を**わざとずらす**。エンジンの name は
            # ファイル名順なので、題名で並べていると気づけない（§8.19）
            app._shelf = [
                {"path": "/x/a.txt", "file": "a.txt", "title": "Z", "url": "u1",
                 "episodes": 10, "mtime": 1, "meta": {"updated": "2020-01-01"}},
                {"path": "/x/b.txt", "file": "b.txt", "title": "Y", "url": "u2",
                 "episodes": 100, "mtime": 2, "meta": {"updated": "2026-09-20"}},
                {"path": "/x/c.txt", "file": "c.txt", "title": "X", "url": "u3",
                 "episodes": 500, "mtime": 3, "meta": {"updated": "2024-05-05"}},
            ]
            for mode, exp in (("name", ["a.txt", "b.txt", "c.txt"]),
                              ("updated", ["b.txt", "c.txt", "a.txt"]),
                              ("episodes", ["c.txt", "b.txt", "a.txt"])):
                app.settings["shelf_sort"] = mode
                got = [r["file"] for r in app._shelf_sorted_works()]
                ck(f"並び順 {mode}（エンジンと同じ基準）", got == exp, str(got))
            # 更新日が無い行は mtime で代用する（タプル比較だと常に最後になる）
            app._shelf.append({"path": "/x/d.txt", "file": "d.txt", "title": "W",
                               "url": "u4", "episodes": 1, "mtime": 10**10,
                               "meta": {}})
            app.settings["shelf_sort"] = "updated"
            got = [r["file"] for r in app._shelf_sorted_works()]
            ck("更新日が無くても mtime で代用する", got[0] == "d.txt", str(got))
            app._shelf.pop()
            ck("既定は更新が新しい順",
               G.load_settings().get("shelf_sort") == "updated")
            app.settings["shelf_sort"] = "updated"
            app._shelf = saved_shelf
            app._refresh_shelf_list()

            # ── 1 件ずつ届いて 1 行だけ直る（§8.17）──
            target = app._shelf_works()[0]
            app._shelf_new = {}
            app._refresh_shelf_list()
            before = [e["state"].cget("text") for e in app._shelf_rows]
            app._shelf_chk_total = len(app._shelf_works())
            app._shelf_chk_done = 0
            app._handle_msg(("checkstart", {"event": "checkstart", "index": 1,
                                            "total": len(app._shelf_works()),
                                            "file": target["file"],
                                            "path": target["path"]}))
            app.pump(0.2)
            idx = app._shelf_row_index(target["path"])
            ck("確認中の行に印が付く",
               app._shelf_rows[idx]["icon"].cget("text") == "⏳")
            ck("確認中だと分かる表示になる",
               "確認中" in app._shelf_rows[idx]["state"].cget("text"),
               app._shelf_rows[idx]["state"].cget("text"))
            others = [i for i in range(len(app._shelf_rows)) if i != idx]
            ck("他の行は変わらない",
               all(app._shelf_rows[i]["state"].cget("text") == before[i]
                   for i in others))

            app._handle_msg(("checkresult", {
                "event": "checkresult", "path": target["path"],
                "file": target["file"], "title": target.get("title", ""),
                "author": "", "existing": 1, "total": 9, "new": 8,
                "status": "updated", "error": ""}))
            app.pump(0.2)
            ck("結果が届いた行だけ新着になる",
               "8" in app._shelf_rows[idx]["state"].cget("text"),
               app._shelf_rows[idx]["state"].cget("text"))
            ck("その行の『続きを取得』が押せるようになる",
               app._shelf_rows[idx]["button"].cget("state") == "normal")
            ck("結果待ちの行は押せないまま",
               all(app._shelf_rows[i]["button"].cget("state") == "disabled"
                   for i in others))
            ck("まとめ取得ボタンが出る", bool(app.btn_shelf_all.winfo_ismapped()))

            # 失敗した作品は失敗と分かる
            app._handle_msg(("checkresult", {
                "event": "checkresult", "path": app._shelf_works()[1]["path"],
                "file": "x", "title": "", "author": "", "existing": 0,
                "total": 0, "new": 0, "status": "error", "error": "だめ"}))
            app.pump(0.2)
            j = app._shelf_row_index(app._shelf_works()[1]["path"])
            ck("確認できなかった行が分かる",
               "確認できず" in app._shelf_rows[j]["state"].cget("text"),
               app._shelf_rows[j]["state"].cget("text"))

            # ── 部分取得のファイルは追記させない（§8.19）──
            saved_new = dict(app._shelf_new)      # 後続の確認が使うので退避
            part = dict(app._shelf_works()[0])
            part.update(path="/x/part.txt", file="part.txt", title="部分作品",
                        meta={"start_offset": 500})
            app._shelf = [part]
            app._shelf_new = {"/x/part.txt": {"new": 400, "status": "updated"}}
            app._refresh_shelf_list()
            app.pump(0.2)
            ck("部分取得だと分かる表示になる",
               "部分" in app._shelf_rows[0]["state"].cget("text"),
               app._shelf_rows[0]["state"].cget("text"))
            ck("新着があっても『続きを取得』を押せない",
               app._shelf_rows[0]["button"].cget("state") == "disabled")
            ck("新着の件数に数えない", app._shelf_new_count() == 0)
            ck("まとめ取得ボタンも出さない",
               not app.btn_shelf_all.winfo_ismapped())
            ck("開始位置を読めている", app._shelf_partial_from(part) == 500)
            ck("壊れた値でも 0 として扱う",
               app._shelf_partial_from({"meta": {"start_offset": "x"}}) == 0)
            app._shelf = saved_shelf
            app._shelf_new = saved_new
            app._refresh_shelf_list()

            # ── 中止できる（§8.17）──
            ck("ふだんは『新着チェック』", "中止" not in app.btn_shelf_check.cget("text"))
            app._shelf_stop = False
            app.btn_shelf_check.configure(text=app._t("shelf_check_stop"),
                                          command=app._shelf_check_cancel)
            app._shelf_check_cancel()
            ck("中止を押すと止める要求が立つ", app._shelf_stop is True)
            app._shelf_chk_done = 2
            app._shelf_check_finished(0)
            app.pump(0.2)
            ck("中止後はボタンが戻る",
               "中止" not in app.btn_shelf_check.cget("text")
               and app.btn_shelf_check.cget("state") == "normal")
            ck("どこまで確認したか残る",
               "2" in app.lbl_shelf_status.cget("text"),
               app.lbl_shelf_status.cget("text"))
            ck("中止しても届いた結果は消えない", app._shelf_new_count() >= 1)

            # ── 走査失敗は「空の本棚」と区別する（§8.12 (2)）──
            # 一度成功していれば、失敗しても**直前の一覧を捨てない**。古くても
            # 妥当な行が残っている方が、空として扱って重複判定を壊すより安全
            before = list(app._shelf)
            app._shelf_scanning = True
            app._inbox_pending = True
            app._inbox_scanning = True
            app._apply_shelf_rows(None)
            ck("走査に失敗しても直前の一覧を捨てない", app._shelf == before)
            ck("走査失敗なら保留中の受信箱走査を畳む",
               app._inbox_pending is False and app._inbox_scanning is False)
            # 初回走査が失敗した場合は土台が無いので loaded を立てない
            app._shelf_loaded = False
            app._shelf = []
            app._apply_shelf_rows(None)
            ck("初回走査の失敗では _shelf_loaded を立てない",
               app._shelf_loaded is False)
            app._apply_shelf_rows([])
            ck("本当に空なら _shelf_loaded を立てる", app._shelf_loaded is True)

            # ── 実行中に二重起動しない（§8.12 (1)）──
            app._jobs = []
            app._proc = "running-dummy"
            added = app._start_or_enqueue(
                app._add_jobs([app._make_job("/tmp/x.txt", kind="append")]))
            ck("実行中でもキューには積む", len(added) == 1 and len(app._jobs) == 1)
            ck("実行中は _proc を奪わない", app._proc == "running-dummy")
            ck("実行中は中止要求を握り潰さない", not app._abort_event.is_set())
            app._proc = None
    finally:
        import shutil
        shutil.rmtree(shelf, ignore_errors=True)

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
