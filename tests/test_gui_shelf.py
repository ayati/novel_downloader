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
