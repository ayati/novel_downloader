# -*- coding: utf-8 -*-
"""実サイトに当てにいくテスト。**既定では走らせない。**

    NOVEL_TEST_NETWORK=1 python3 tests/run_all.py

サイトへ余計な負荷をかけないよう件数は最小限にしてある。ここが落ちたときは
サイト側の変更が疑われるので、`novel_health_check.py` も併せて走らせる。
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Checker, NETWORK, REPO  # noqa: E402

ENGINE = [sys.executable, os.path.join(REPO, "novel_downloader.py")]
TANPEN = "https://ncode.syosetu.com/n9801mn/"      # 全1話の短編
SERIAL = "https://ncode.syosetu.com/n0022gd/"      # 連載


def run(args, timeout=180):
    return subprocess.run(ENGINE + args, capture_output=True, timeout=timeout,
                          text=True, encoding="utf-8", errors="replace")


def events(out: str, name: str) -> list:
    got = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("event") == name:
            got.append(ev)
    return got


def main() -> int:
    ck = Checker("ネットワーク")
    if not NETWORK:
        ck.skip("NOVEL_TEST_NETWORK=1 のときだけ走ります")
        return ck.done()

    # ── なろうの短編（目次が無い作品）──
    r = run([TANPEN, "--dry-run", "--progress-json"])
    wi = events(r.stdout, "workinfo")
    ck("短編でも作品情報が取れる", bool(wi) and wi[0].get("total") == 1,
       str(wi[:1]))
    ck("短編で終了コードが 0", r.returncode == 0)

    # ── 連載（回帰の目印）──
    r = run([SERIAL, "--dry-run", "--progress-json"])
    wi = events(r.stdout, "workinfo")
    ck("連載の作品情報が取れる", bool(wi) and (wi[0].get("total") or 0) > 1)
    ck("stage が 3 段流れる",
       len({e["n"] for e in events(r.stdout, "stage")}) >= 2)
    ck("workinfo に展開後の URL が載る",
       bool(wi) and wi[0].get("url", "").startswith("https://ncode.syosetu.com/"))

    # ── 存在しない作品は 1 行のエラーで終わる ──
    r = run(["https://ncode.syosetu.com/n9999zzz/", "--dry-run"])
    err = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith("エラー: ")]
    ck("404 はスタックトレースでなく 1 行のエラー", bool(err), err[:1])
    ck("404 の終了コードは 1", r.returncode == 1)
    ck("トレースバックを既定で出さない",
       "Traceback (most recent call last)" not in (r.stdout + r.stderr))

    # ── 短編を実際に落として ePub まで作る ──
    with tempfile.TemporaryDirectory() as d:
        r = run([TANPEN, "--output-dir", d], timeout=300)
        ck("短編をダウンロードできる", r.returncode == 0)
        txts = [f for f in os.listdir(d) if f.endswith(".txt")]
        epubs = [f for f in os.listdir(d) if f.endswith(".epub")]
        ck("テキストと ePub が出る", len(txts) == 1 and len(epubs) == 1,
           str(os.listdir(d)))
        if txts:
            body = open(os.path.join(d, txts[0]), encoding="utf-8").read()
            ck("大見出しが 1 つ", body.count("は大見出し］") == 1)
            ck("底本URL が入る", "底本URL：" in body)

    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
