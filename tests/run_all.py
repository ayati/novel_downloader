#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/ の test_*.py をまとめて走らせる。

    python3 tests/run_all.py            # オフラインのみ（既定・数十秒）
    NOVEL_TEST_NETWORK=1 python3 tests/run_all.py
    python3 tests/run_all.py gui        # 名前に gui を含むものだけ

各テストは**別プロセス**で走らせる。GUI テストは Tk のウィンドウを作るため、
同一プロセスで続けて走らせると前のテストの後始末に引きずられる。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    pat = sys.argv[1] if len(sys.argv) > 1 else ""
    files = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py") and pat in f)
    if not files:
        print(f"該当するテストがありません: {pat!r}")
        return 2
    t0 = time.time()
    failed = []
    for f in files:
        r = subprocess.run([sys.executable, os.path.join(HERE, f)])
        if r.returncode != 0:
            failed.append(f)
    print("\n" + "=" * 60)
    print(f" {len(files) - len(failed)} / {len(files)} スイート成功"
          f"   ({time.time() - t0:.1f}s)")
    if failed:
        print(" 失敗:", ", ".join(failed))
    if os.environ.get("NOVEL_TEST_NETWORK") != "1":
        print(" ※ ネットワークテストは省略（NOVEL_TEST_NETWORK=1 で有効）")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
