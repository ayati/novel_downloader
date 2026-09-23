# -*- coding: utf-8 -*-
"""Webhook 設定の画面操作（design_gui_v2 §8.13a）。

**ウィジェットを操作して画面がどうなるかで書く。** 関数を呼んで戻り値を見る
書き方だと、実機で踏んだ「チェックが入らない・URL を貼れない」詰みを
取り逃す（実際に取り逃した）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, gui_app, gui_available  # noqa: E402

URL = "https://discord.com/api/webhooks/123/abc"


def main() -> int:
    ck = Checker("GUI・Webhook 設定")
    avail, why = gui_available()
    if not avail:
        ck.skip(why)
        return ck.done()

    with gui_app() as (G, app):
        job = app._make_job("https://ncode.syosetu.com/n0022gd/")

        def args():
            return app._build_cli_args(job, app._collect_settings())

        ck("初期状態は OFF・注意書きなし",
           app.var_notify.get() is False and not app.lbl_webhook_hint.winfo_ismapped())
        ck("OFF のとき URL 欄は使えない", app.ent_webhook.cget("state") == "disabled")

        # 実機の操作順: まずチェックを入れる（宛先はまだ空）
        app.chk_notify.toggle(); app.pump()
        ck("チェックを入れたら ON のままになる", app.var_notify.get() is True)
        ck("チェックを入れると URL 欄に貼れる",
           app.ent_webhook.cget("state") == "normal")
        ck("宛先が無いことを注意書きで知らせる",
           bool(app.lbl_webhook_hint.winfo_ismapped()))
        ck("宛先が無い間は通知引数を渡さない", "--notify" not in args())

        app.var_webhook_url.set("not-a-url"); app._on_notify_changed(); app.pump()
        ck("形式が違えば渡さない", "--notify" not in args())
        ck("入力した文字を勝手に消さない", app.var_webhook_url.get() == "not-a-url")
        ck("形式が違う間も注意書きが出る",
           bool(app.lbl_webhook_hint.winfo_ismapped()))

        app.var_webhook_url.set(URL); app._on_notify_changed(); app.pump()
        ck("正しい URL で注意書きが消える",
           not app.lbl_webhook_hint.winfo_ismapped())
        a = args()
        ck("通知引数が 3 点セットで渡る",
           a[a.index("--notify") + 1] == "webhook"
           and a[a.index("--webhook-url") + 1] == URL)
        app.var_webhook_fmt.set("slack"); app._on_notify_changed()
        ck("slack を選べる",
           args()[args().index("--webhook-format") + 1] == "slack")
        ck("append ジョブにも付く",
           "--notify" in app._build_cli_args(
               app._make_job("/tmp/x.txt", kind="append"), app._collect_settings()))
        ck("本棚の新着チェックにも付く",
           "--notify" in G.engine_cmd("--check-update-dir", "/tmp", "--progress-json",
                                      *G._webhook_args(app._collect_settings())))
        saved = G.load_settings()
        ck("設定が保存される",
           saved.get("notify_webhook") is True and saved.get("webhook_url") == URL
           and saved.get("webhook_format") == "slack")

        app.chk_notify.toggle(); app.pump()
        ck("切ると URL 欄が無効になる", app.ent_webhook.cget("state") == "disabled")
        ck("切ると注意書きも消える", not app.lbl_webhook_hint.winfo_ismapped())
        ck("切ると通知引数が消える", "--notify" not in args())
        ck("切っても宛先は残る（入れ直さなくてよい）",
           app.var_webhook_url.get() == URL)

        # 挿絵の取り込み停止（§8.13 (3)）
        app.var_no_images.set(True); app._persist()
        ck("挿絵を取り込まない設定が渡る", "--no-inline-images" in args())
        app.var_no_images.set(False); app._persist()
        ck("既定では渡さない", "--no-inline-images" not in args())

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
