# -*- coding: utf-8 -*-
"""GUI のうち、ウィンドウを開かずに確かめられる部分。

画面が無い環境でも走る（customtkinter が import できれば十分）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker  # noqa: E402


def main() -> int:
    ck = Checker("GUI（純粋関数）")
    try:
        import novel_downloader_gui as G
    except Exception as e:
        ck.skip(f"novel_downloader_gui を import できない（{e}）")
        return ck.done()

    # ── 重複判定の URL 畳み込み（§8.12 (3)）──
    c = G.canon_url
    ck("末尾スラッシュの有無を吸収",
       c("https://ncode.syosetu.com/n9623lp") == c("https://ncode.syosetu.com/n9623lp/"))
    ck("ncode の大文字を吸収",
       c("https://ncode.syosetu.com/N9623LP/") == c("https://ncode.syosetu.com/n9623lp/"))
    ck("別作品は一致しない",
       c("https://ncode.syosetu.com/n0022gd/") != c("https://ncode.syosetu.com/n9623lp/"))

    # ── 未対応の判定（§8.8）──
    ck("短縮URLを『未対応』と決めつけない",
       G.is_unsupported({"site": None, "short_url": True}) is False)
    ck("本当に未対応なら未対応",
       G.is_unsupported({"site": None, "short_url": False}) is True)
    ck("判定できなかった場合も未対応扱い", G.is_unsupported(None) is True)

    # ── Webhook（§8.13a）──
    ck("書式を整えるだけで、チェックを勝手に戻さない",
       G.normalize_webhook({"notify_webhook": True, "webhook_url": ""})["notify_webhook"] is True)
    ck("入力中の値を消さない",
       G.normalize_webhook({"webhook_url": "not-a-url"})["webhook_url"] == "not-a-url")
    ck("前後の空白は落とす",
       G.normalize_webhook({"webhook_url": "  https://x/y  "})["webhook_url"] == "https://x/y")
    ck("形式の enum を矯正する",
       G.normalize_webhook({"webhook_format": "teams"})["webhook_format"] == "discord")
    ck("使えるかの判定は webhook_ready が持つ",
       G.webhook_ready({"notify_webhook": True, "webhook_url": "x"}) is False
       and G.webhook_ready({"notify_webhook": True,
                            "webhook_url": "https://x/y"}) is True)
    ck("宛先が無ければ CLI 引数を出さない（エンジンを落とさない）",
       G._webhook_args({"notify_webhook": True, "webhook_url": ""}) == [])
    args = G._webhook_args({"notify_webhook": True, "webhook_url": "https://x/y",
                            "webhook_format": "slack"})
    ck("揃えば 3 点セットで出す",
       args == ["--notify", "webhook", "--webhook-url", "https://x/y",
                "--webhook-format", "slack"], str(args))

    # ── 受信箱のファイル読み（§8.11）──
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.txt")
        open(p, "w", encoding="utf-8").write("https://example.com/x\n")
        ck("UTF-8 のメモを読める", "example.com" in G.read_text_any(p))
        p2 = os.path.join(d, "sjis.txt")
        open(p2, "wb").write("日本語 https://example.com/y\n".encode("cp932"))
        ck("cp932 のメモも読める", "example.com" in G.read_text_any(p2))
        p3 = os.path.join(d, "bin.png")
        open(p3, "wb").write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64)
        ck("バイナリは本文として読まない（NUL を含む）", G.read_text_any(p3) == "")
        p4 = os.path.join(d, "big.txt")
        open(p4, "w", encoding="utf-8").write("x" * (G.INBOX_MAX_BYTES + 1))
        ck("大きすぎるファイルは読まない", G.read_text_any(p4) == "")
        ck("読めないパスでも落ちない", G.read_text_any(os.path.join(d, "none")) == "")

    # ── URL の取り出し（§7.2）──
    ex = G.NovelDownloaderApp._extract_urls
    ck("本文混じりから拾える",
       ex("これ読む https://ncode.syosetu.com/n1/ あとで") == ["https://ncode.syosetu.com/n1/"])
    ck("複数を順序どおり・重複は畳む",
       ex("https://a.example/1 https://b.example/2 https://a.example/1")
       == ["https://a.example/1", "https://b.example/2"])
    ck("文末の記号を巻き込まない",
       ex("見つけた https://a.example/1。") == ["https://a.example/1"])
    ck("URL が無ければ空", ex("ただのメモ") == [])

    # ── パネルの高さ配分（§8.5）──
    A = G.NovelDownloaderApp._allocate_heights
    spec = [[None, 150, 90, 40]] * 3 + [[None, 300, 120, 60]]
    ck("全部入るなら希望どおり", A(spec, 10000) == [150, 150, 150, 300])
    r = A(spec, 500)
    ck("入らなければ下限を満たしつつ収める",
       sum(r) <= 500 and all(r[i] >= spec[i][2] for i in range(4)), str(r))
    r = A(spec, 300)
    ck("下限も入らなければ絶対最小まで詰める",
       sum(r) <= 300 and all(r[i] >= spec[i][3] for i in range(4)), str(r))
    ck("極端に狭くても正の高さを返す", all(x > 0 for x in A(spec, 10)))
    ck("パネル 0 枠でも落ちない", A([], 500) == [])

    # ── エンジンへ渡す言語（§8.13）──
    G.set_engine_lang("en")
    ck("English を伝える", G._engine_env()["NOVEL_DOWNLOADER_LANG"] == "en")
    G.set_engine_lang("ja")
    ck("日本語に戻せる", G._engine_env()["NOVEL_DOWNLOADER_LANG"] == "ja")
    ck("想定外の値は日本語に倒す",
       (G.set_engine_lang("zh"), G._engine_env()["NOVEL_DOWNLOADER_LANG"])[1] == "ja")

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
