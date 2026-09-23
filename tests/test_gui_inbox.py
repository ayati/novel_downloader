# -*- coding: utf-8 -*-
"""受信箱（design_gui_v2 §8.3 / §8.10 / §8.11）。ネットワーク不要。

本棚にすでにある URL だけを置くことで、作品情報の先読み（--dry-run）へ
進まないようにしている。短縮URLの展開を含む経路は test_network.py 側。
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, gui_app, gui_available, make_memo, make_work_txt  # noqa: E402

NCODE = "n0001aa"
URL = f"https://ncode.syosetu.com/{NCODE}/"


def main() -> int:
    ck = Checker("GUI・受信箱")
    avail, why = gui_available()
    if not avail:
        ck.skip(why)
        return ck.done()

    shelf = tempfile.mkdtemp(prefix="ndtest_shelf_")
    inbox = tempfile.mkdtemp(prefix="ndtest_inbox_")
    make_work_txt(shelf, "A.txt", "作品A", NCODE, episodes=2)
    make_memo(inbox, "memo.txt", f"出先メモ {URL} あとで読む\n")
    make_memo(inbox, "nourl.txt", "URL の無いただのメモ\n")
    with open(os.path.join(inbox, "shot.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    try:
        with gui_app(output_dir=shelf, inbox_dir=inbox) as (G, app):
            app._toggle_inbox()
            app._inbox_reload()
            if not app.wait(lambda: not app._inbox_scanning and app._inbox, 120):
                ck("受信箱の走査が終わる", False)
                return ck.done()

            urls = [it for it in app._inbox if it["url"]]
            nourl = [it for it in app._inbox if not it["url"]]
            ck("URL を拾う", len(urls) == 1, str([it["url"] for it in urls]))
            ck("URL の無いファイルは消さずに残す（PNG とメモの 2 件）",
               len(nourl) == 2, str(sorted(it["file"] for it in nourl)))
            ck("本棚にある作品は『取得済み』になる", urls[0]["have"] is True)
            ck("取得済みは選択が外れる", urls[0]["sel"].get() is False)
            ck("選択ゼロなら取得ボタンを押せない",
               app.btn_inbox_fetch.cget("state") == "disabled")
            ck("本棚を待ってから重複判定する（起動直後でも取得済みが分かる）",
               app._shelf_loaded is True)

            # ── 話の一覧（§8.15）──
            row0 = app._inbox_rows[0]
            ck("取得済みの行では一覧ボタンを押せない（本棚から見られる）",
               row0["list"].cget("state") == "disabled")
            ck("_inbox_can_list が取得済みを弾く",
               app._inbox_can_list(row0["row"]) is False)
            ck("URL の無い行には一覧ボタンを出さない",
               len(app._inbox_rows) == 1 and len(app._inbox) == 3)

            base = dict(row0["row"])
            for flag, want in (("have", False), ("unsupported", False),
                               ("checking", False)):
                probe = dict(base); probe.update(have=False, unsupported=False,
                                                 checking=False)
                probe[flag] = True
                ck(f"{flag} の行は一覧を出せない",
                   app._inbox_can_list(probe) is want)
            fetchable = dict(base)
            fetchable.update(have=False, unsupported=False, checking=False)
            ck("未取得で判定済みの行は一覧を出せる",
               app._inbox_can_list(fetchable) is True)
            ck("URL が無ければ出せない",
               app._inbox_can_list(dict(fetchable, url="")) is False)

            # 実際に一覧を開く（エンジンは呼ばずに差し替える＝通信しない）
            captured = {}
            real = G.episode_list

            def fake(target, from_file=False, timeout=300):
                captured.update(target=target, from_file=from_file)
                return {"title": "作品X", "author": "著者X", "total": 2,
                        "titles": ["第1話", "第2話"]}

            G.episode_list = fake
            try:
                item = dict(fetchable)
                item.update(resolved="https://kakuyomu.jp/works/1",
                            url="https://share.google/abc",
                            sel=G.ctk.BooleanVar(value=True))
                app._inbox = [item]
                app._refresh_inbox_list()
                app._inbox_show_episodes(item)
                ck("一覧の読み込みが終わる",
                   app.wait(lambda: not app._inbox_listing, 60))
                ck("短縮URLではなく展開後のURLに問い合わせる",
                   captured.get("target") == "https://kakuyomu.jp/works/1",
                   str(captured.get("target")))
                ck("受信箱はサイトに問い合わせる（--from-file ではない）",
                   captured.get("from_file") is False)
                wins = [w for w in app.winfo_children()
                        if w.winfo_class() == "Toplevel"]
                ck("一覧の窓が開く", len(wins) >= 1)

                # ── ここから取得（§8.16）──
                win = wins[-1]
                ck("受信箱の窓には『ここから取得』がある",
                   hasattr(win, "start_button") and hasattr(win, "select_line"))
                ck("行を選ぶまでは押せない",
                   win.start_button.cget("state") == "disabled")
                win.select_line(2)
                app.pump(0.2)
                ck("行を選ぶと押せるようになる",
                   win.picked == 2 and win.start_button.cget("state") == "normal")
                ck("選んだ番号がボタンに出る",
                   "2" in win.start_button.cget("text"), win.start_button.cget("text"))
                win.select_line(999)
                ck("範囲外を選んでも変わらない", win.picked == 2)

                app._jobs = []
                app._proc = "busy"            # 積むだけで走らせない
                win.start_button.cget("command")()
                app.pump(0.2)
                ck("ジョブが 1 件積まれる", len(app._jobs) == 1, str(len(app._jobs)))
                if app._jobs:
                    j = app._jobs[0]
                    ck("ジョブに開始位置が入る", j.get("start") == 2, str(j.get("start")))
                    cli = app._build_cli_args(j, app._collect_settings())
                    ck("--start が CLI に載る",
                       "--start" in cli and cli[cli.index("--start") + 1] == "2",
                       " ".join(cli[:4]))
                    ck("--end は付けない（常に最新まで）", "--end" not in cli)
                    ck("受信箱由来の印が残る（done へ移すため）",
                       j.get("inbox_file") == item["path"])
                    app._refresh_queue_list()
                    ck("一覧の行に開始位置が出る",
                       "2" in app._queue_rows[0]["label"].cget("text"),
                       app._queue_rows[0]["label"].cget("text"))
                app._proc = None
                for w in wins:
                    try:
                        w.destroy()
                    except Exception:
                        pass
            finally:
                G.episode_list = real

            # ── 走査を見送る条件（§8.10）──
            app._proc = "dummy"
            ck("ダウンロード中は走査しない", app._inbox_maybe_scan() is False)
            app._proc = None
            app._shelf_proc = "dummy"
            ck("本棚チェック中は走査しない", app._inbox_maybe_scan() is False)
            app._shelf_proc = None
            app._inbox_last_scan = time.time()
            ck("フォーカス連打では走査しない",
               app._inbox_maybe_scan(min_gap=30.0) is False)

            # ── 定期スキャンの予約（§8.10）──
            app.settings["inbox_scan_min"] = 0
            app._inbox_schedule()
            ck("間隔 0 なら予約しない", app._inbox_after is None)
            app.settings["inbox_scan_min"] = 5
            app._inbox_schedule()
            ck("戻せば予約し直す", app._inbox_after is not None)

            # ── 自動取得は同じファイルを叩き続けない（§8.12 (7)）──
            app._jobs = []
            app._inbox_tried = set()
            app._proc = "busy"          # 積むだけで走らせない
            item = dict(app._inbox[0])
            item.update(url="https://kakuyomu.jp/works/1", have=False,
                        path=os.path.join(inbox, "memo.txt"),
                        sel=G.ctk.BooleanVar(value=True), unsupported=False,
                        site_info=None, title="", resolved="")
            app._inbox = [item]
            app._inbox_fetch_selected(auto=True)
            n = len(app._jobs)
            ck("積めたら『試した』印が付く", item["path"] in app._inbox_tried)
            app._inbox_tried.discard(item["path"])
            app._inbox_fetch_selected(auto=True)
            ck("重複で捨てられたら印を付けない",
               item["path"] not in app._inbox_tried and len(app._jobs) == n)
            app._proc = None

            # ── done へ移動（§8.3 / §8.11）──
            victim = tempfile.mkdtemp(prefix="ndtest_victim_")
            try:
                os.symlink(victim, os.path.join(inbox, "done"))
                src = make_memo(inbox, "evil.txt", "https://example.com/x\n")
                app._inbox_move_done(src)
                ck("done が symlink なら移動しない", os.path.isfile(src))
                ck("リンク先に書き込まない", os.listdir(victim) == [])
                os.remove(os.path.join(inbox, "done"))
                app._inbox_move_done(src)
                ck("通常の done へは移動できる",
                   os.path.isfile(os.path.join(inbox, "done", "evil.txt"))
                   and not os.path.exists(src))
            except (OSError, NotImplementedError):
                ck.skip("symlink を作れない環境")
            finally:
                shutil.rmtree(victim, ignore_errors=True)
    finally:
        shutil.rmtree(shelf, ignore_errors=True)
        shutil.rmtree(inbox, ignore_errors=True)

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
