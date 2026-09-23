# -*- coding: utf-8 -*-
"""テスト共通ヘルパー。

外部ライブラリは使わない（pytest 等を増やさない）。各 test_*.py は単体でも
実行でき、`python3 tests/run_all.py` でまとめて走らせられる。
"""
import contextlib
import json
import os
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# ネットワークを使うテストは既定で走らせない（サイトに当てにいくため）。
# 走らせるときは NOVEL_TEST_NETWORK=1。
NETWORK = os.environ.get("NOVEL_TEST_NETWORK") == "1"


class Checker:
    """assert を使わず、全項目を最後まで走らせて結果を集計する。

    1 件目で止まると「他も壊れているのか」が分からず、実機での確認と
    突き合わせにくい。
    """

    def __init__(self, title: str):
        self.title = title
        self.ok: list[str] = []
        self.ng: list[str] = []
        print(f"\n── {title} ──")

    def __call__(self, name: str, cond, detail: str = "") -> bool:
        cond = bool(cond)
        (self.ok if cond else self.ng).append(name)
        print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
        return cond

    def skip(self, reason: str) -> int:
        print(f"  SKIP  {reason}")
        return 0

    def done(self) -> int:
        print(f"=== {self.title}: OK {len(self.ok)} / FAIL {len(self.ng)} ===")
        if self.ng:
            print("  失敗:", ", ".join(self.ng))
        return 1 if self.ng else 0


def gui_available() -> tuple[bool, str]:
    """GUI を起動できる環境か。できない理由も返す。"""
    try:
        import customtkinter  # noqa: F401
    except Exception as e:
        return False, f"customtkinter が入っていない（{e}）"
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        return False, "DISPLAY が無い（ヘッドレス）"
    return True, ""


def make_work_txt(directory: str, filename: str, title: str,
                  ncode: str = "n0001aa", episodes: int = 1,
                  meta: dict = None) -> str:
    """本棚テスト用の青空文庫書式 .txt を作る。

    **書式はエンジン自身の関数で組み立てる。** 区切り線やヘッダーをテスト側で
    書き写すと、本体が書式を変えたときにテストだけ古い形を作り続け、
    「通っているのに実体とずれている」状態になる。
    """
    import novel_downloader as N
    url = f"https://ncode.syosetu.com/{ncode}/"
    m = {"site": "小説家になろう"}
    m.update(meta or {})
    header = N.aozora_header(title, "著者名", "あらすじ", source_url=url, meta=m)
    sections = [f"{N.aozora_chapter_title(f'第{i}話')}\n\n本文{i}\n"
                for i in range(1, episodes + 1)]
    colophon = N.aozora_colophon(title, url, "小説家になろう")
    path = os.path.join(directory, filename)
    N.write_file(path, header, sections, colophon)
    return path


def make_memo(directory: str, filename: str, body: str) -> str:
    """受信箱テスト用のメモファイルを作る。"""
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


@contextlib.contextmanager
def gui_app(**settings):
    """隔離した設定で GUI を起動し、後片付けまで面倒を見る。

    - 設定ファイルは一時ディレクトリへ逃がす（実ユーザーの settings.json を触らない）
    - **完了時のフォルダ自動オープンは必ず切る。** `_open_folder()` は
      `subprocess.run()` をタイムアウト無しで呼ぶため、WSL では `xdg-open` が
      ブラウザを起こして戻ってこずテストが固まる（design_gui_v2.md §8.14）
    """
    cfg = tempfile.mkdtemp(prefix="ndtest_cfg_")
    saved = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "APPDATA")}
    os.environ["XDG_CONFIG_HOME"] = cfg
    os.environ["APPDATA"] = cfg
    import novel_downloader_gui as G
    seed = {"schema": G.SETTINGS_SCHEMA, "open_folder_on_done": False,
            "auto_paste": False, "inbox_scan_min": 0}
    seed.update(settings)
    os.makedirs(os.path.dirname(G.settings_path()), exist_ok=True)
    with open(G.settings_path(), "w", encoding="utf-8") as f:
        json.dump(seed, f)
    app = G.NovelDownloaderApp()
    app.pump = lambda sec=0.3: _pump(app, sec)
    app.wait = lambda fn, sec=60: _wait(app, fn, sec)
    app.pump(0.5)
    try:
        yield G, app
    finally:
        app._closing = True
        try:
            app.destroy()
        except Exception:
            pass
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import shutil
        shutil.rmtree(cfg, ignore_errors=True)


def _pump(app, sec: float):
    end = time.time() + sec
    while time.time() < end:
        try:
            app.update()
        except Exception:
            return
        time.sleep(0.02)


def _wait(app, fn, sec: float) -> bool:
    end = time.time() + sec
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        _pump(app, 0.1)
    return False
