# -*- coding: utf-8 -*-
"""おまかせ表紙のフォント（--cover-font）の画面操作。

**ウィジェットを操作して画面がどうなるかで書く**（tests/README.md）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, gui_app, gui_available  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "font", "AyatiShowaSerif-Regular.ttf")


def main() -> int:
    ck = Checker("GUI・表紙フォント")
    avail, why = gui_available()
    if not avail:
        ck.skip(why)
        return ck.done()
    if not os.path.exists(FONT):
        ck.skip("font/AyatiShowaSerif-Regular.ttf が無い")
        return ck.done()

    with gui_app() as (G, app):
        job = app._make_job("https://ncode.syosetu.com/n0022gd/")

        def args():
            return app._build_cli_args(job, app._collect_settings())

        ck("初期状態はおまかせ・標準フォント",
           app.var_cover.get() == "auto"
           and app.var_cover_font_name.get() == app._t("cover_font_default"))
        ck("おまかせのときは表紙フォントを選べる",
           app.btn_cover_font_pick.cget("state") == "normal")
        ck("未設定なら --cover-font を渡さない（起動コマンドは従来どおり）",
           "--cover-font" not in args())

        # 「選ぶ」を押してファイルを選んだ体で進める
        orig = G.filedialog.askopenfilename
        G.filedialog.askopenfilename = lambda **kw: FONT
        try:
            app.btn_cover_font_pick.invoke(); app.pump()
        finally:
            G.filedialog.askopenfilename = orig
        ck("選んだフォント名が表示される",
           app.var_cover_font_name.get() == os.path.basename(FONT))
        a = args()
        ck("選んだフォントがエンジンに渡る",
           "--cover-font" in a and a[a.index("--cover-font") + 1] == FONT)
        ck("続きを取得（append）にも渡る",
           "--cover-font" in app._build_cli_args(
               app._make_job("/tmp/x.txt", kind="append"), app._collect_settings()))
        ck("設定が保存される",
           G.load_settings().get("cover_font_path") == FONT)

        # 公式表紙・自分の画像に切り替えると、表紙フォントは意味を持たない
        app.rad_cover_site.invoke(); app.pump()
        ck("公式表紙のときは表紙フォントを選べない",
           app.btn_cover_font_pick.cget("state") == "disabled")
        ck("公式表紙のときは --cover-font を渡さない", "--cover-font" not in args())
        app.rad_cover_auto.invoke(); app.pump()
        ck("おまかせに戻すと選んだフォントがそのまま使われる",
           "--cover-font" in args())

        app.btn_cover_font_clear.invoke(); app.pump()
        ck("標準に戻すと表示も戻る",
           app.var_cover_font_name.get() == app._t("cover_font_default"))
        ck("標準に戻すと --cover-font を渡さない", "--cover-font" not in args())
        ck("標準に戻したことも保存される",
           G.load_settings().get("cover_font_path") == "")

        # 保存していたフォントが消えていたら標準で起動する。gui_app を 2 度
        # 起動すると前の窓の after が残って Tk が騒ぐので、設定の読み直しで確かめる
        import json
        with open(G.settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        data["cover_font_path"] = "/no/such/font.ttf"
        with open(G.settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)
        ck("消えたフォントは標準に戻して起動する",
           G.load_settings().get("cover_font_path") == "")

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
