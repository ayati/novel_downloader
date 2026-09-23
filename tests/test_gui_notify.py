# -*- coding: utf-8 -*-
"""完了の知らせ（design_gui_v2 §8.18）。ネットワーク不要。

**「窓を見ていないときだけ光る／鳴る」**が要点なので、フォーカス状態を
切り替えて両方の側を確かめる。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, gui_app, gui_available  # noqa: E402


def main() -> int:
    ck = Checker("GUI・完了の知らせ")
    avail, why = gui_available()
    if not avail:
        ck.skip(why)
        return ck.done()

    import novel_downloader_gui as G
    ck("Windows 以外では点滅させず、落ちもしない",
       G.flash_taskbar(None) is False or os.name == "nt")

    with gui_app() as (G, app):
        base = app._t("title")
        ck("初期状態のタイトルに知らせは無い", app.title() == base, app.title())

        flashed, real_flash = [], G.flash_taskbar
        belled = []
        G.flash_taskbar = lambda w: flashed.append(1) or True
        app.bell = lambda: belled.append(1)
        try:
            # ── 見ているとき: タイトルだけ ──
            app._focused = True
            app._notify("notice_done", n=3)
            app.pump(0.1)
            ck("タイトルに結果が出る", "3" in app.title() and base in app.title(),
               app.title())
            ck("見ているときは光らせない", flashed == [])
            ck("見ているときは鳴らさない", belled == [])

            # ── 見ていないとき: 光る ──
            app._focused = False
            app._notify("notice_done", n=5)
            app.pump(0.1)
            ck("見ていないときは光る", len(flashed) == 1)
            ck("音は既定では鳴らさない", belled == [])

            app.settings["notify_sound"] = True
            app._notify("notice_failed")
            app.pump(0.1)
            ck("設定を入れれば鳴る", len(belled) == 1)
            ck("失敗も知らせる", "⚠" in app.title(), app.title())

            app.settings["notify_taskbar"] = False
            n_before = len(flashed)
            app._notify("notice_done", n=1)
            ck("設定を切れば光らない", len(flashed) == n_before)
            app.settings["notify_taskbar"] = True

            # ── 見たら知らせは消える ──
            class E:
                widget = app
            app._on_focus_in(E())
            app.pump(0.1)
            ck("窓を見たらタイトルが元に戻る", app.title() == base, app.title())
            ck("見たので _focused が立つ", app._focused is True)

            # ── 各場面で知らせが出るか ──
            app._focused = False
            app._epub_path = None
            app._set_state_done()
            ck("1 件の完了で知らせる", "✅" in app.title(), app.title())

            app._raw_log = ["エラー: なにか"]
            app._set_state_error("failed")
            ck("失敗で知らせる", "⚠" in app.title(), app.title())

            app._shelf_new = {"/x/a.txt": {"new": 4, "status": "updated"}}
            app._shelf = [{"path": "/x/a.txt", "url": "u", "title": "A",
                           "episodes": 1, "meta": {}}]
            app._shelf_stop = False
            app._shelf_chk_done = 1
            app._shelf_check_finished(0)
            app.pump(0.1)
            ck("新着チェックの結果を知らせる", "🆕" in app.title(), app.title())

            app._shelf_new = {}
            app._shelf_check_finished(0)
            app.pump(0.1)
            ck("新着が無くても終わりを知らせる",
               "新着なし" in app.title(), app.title())

            # 中止したときは知らせない（利用者が止めたので分かっている）
            app._shelf_stop = True
            app._notice = ""
            app._sync_title()
            app._shelf_check_finished(0)
            app.pump(0.1)
            ck("中止したときは知らせない", app.title() == base, app.title())
        finally:
            G.flash_taskbar = real_flash

        # ウィジェット → 保存 → 読み込みの往復を見る
        app.var_flash.set(False)
        app.var_sound.set(True)
        app._persist()
        saved = G.load_settings()
        ck("設定が保存される",
           saved.get("notify_taskbar") is False and saved.get("notify_sound") is True,
           f"taskbar={saved.get('notify_taskbar')} sound={saved.get('notify_sound')}")
        app.var_flash.set(True)
        app.var_sound.set(False)
        app._persist()
        ck("既定へ戻せる",
           G.load_settings().get("notify_taskbar") is True
           and G.load_settings().get("notify_sound") is False)
        ck("設定のチェックボックスがある",
           hasattr(app, "chk_flash") and hasattr(app, "chk_sound"))

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
