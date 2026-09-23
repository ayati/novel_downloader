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
