"""Android アプリと novel_downloader.py の橋渡し層。

Kotlin 側からは Chaquopy 経由で detect() / run() / cancel() を呼ぶ。
本体（novel_downloader.py）の GUI 連携 API（ABORT_EVENT / PROGRESS_CALLBACK /
main(argv) / NOVEL_DL_COVER_FONT）にのみ依存し、それ以外へ干渉しない。

注意: novel_downloader は import 時に表紙フォント探索を行うため、
Kotlin 側は Python 起動前（Python.start より前）に環境変数
NOVEL_DL_COVER_FONT を設定しておくこと。
"""
import contextlib
import io
import json
import sys
import traceback

import novel_downloader as nd


def detect(url: str) -> str:
    """URL のサイト種別を判定して JSON 1行を返す（--detect-site と同一スキーマ）。

    オフライン・即時。短縮URL展開はしない（本体 main() が実行時に展開する）。
    """
    res = {"schema": 1, "site": None, "display_name": None,
           "needs_playwright": False, "normalized_url": None}
    try:
        site = nd.detect_site(url)
        if site != "unknown" and site in nd._SITE_DISPATCH:
            # normalize_url は話数URLで [情報]… を print するため stdout を抑制
            with contextlib.redirect_stdout(io.StringIO()):
                norm = nd.normalize_url(url, site)
            res.update(site=site,
                       display_name=nd._SITE_DISPATCH[site][0],
                       needs_playwright=(site == "hameln"),
                       normalized_url=norm)
    except Exception:
        pass  # 解析不能は site=None のまま返す
    return json.dumps(res, ensure_ascii=False)


class _LineWriter(io.TextIOBase):
    """write() を行単位に束ねて emit コールバックへ流す TextIO。"""

    def __init__(self, emit):
        self._emit = emit
        self._buf = ""

    def write(self, s):
        self._buf += str(s)
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit_safe(line)
        return len(s)

    def flush(self):
        if self._buf:
            self._emit_safe(self._buf)
            self._buf = ""

    def _emit_safe(self, line):
        try:
            self._emit(line)
        except Exception:
            pass  # リスナー側の例外でダウンロードを止めない


def run(url: str, options_json: str, listener) -> int:
    """ダウンロードを実行して終了コードを返す（0=成功 / 130=中止 / 他=エラー）。

    listener は Kotlin 側の DownloadListener:
      onLine(text)・onProgress(n, total)・onPhase(phase)
    """
    opts = json.loads(options_json or "{}")
    argv = [url, "--output-dir", opts["output_dir"]]
    if opts.get("horizontal"):
        argv.append("--horizontal")
    if opts.get("kobo"):
        argv.append("--kobo")
    if opts.get("use_site_cover"):
        argv.append("--use-site-cover")

    state = {"phase": "PREPARING"}
    listener.onPhase("PREPARING")

    def on_progress(n, total, title):
        if state["phase"] == "PREPARING":
            state["phase"] = "DOWNLOADING"
            listener.onPhase("DOWNLOADING")
        if n >= total and state["phase"] == "DOWNLOADING":
            state["phase"] = "SAVING"
        listener.onProgress(n, total)

    def on_line(line):
        # 本文DL終了後の書き出し・ePub生成フェーズを検出する
        if state["phase"] != "SAVING" and (
                "テキスト出力完了" in line or "ePub生成中" in line):
            state["phase"] = "SAVING"
            listener.onPhase("SAVING")
        listener.onLine(line)

    out = _LineWriter(on_line)
    old_stdout, old_stderr = sys.stdout, sys.stderr
    nd.ABORT_EVENT.clear()
    nd.PROGRESS_CALLBACK = on_progress
    sys.stdout = sys.stderr = out
    try:
        nd.main(argv)
        return 0
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    except BaseException:
        out.write(traceback.format_exc())
        return 1
    finally:
        out.flush()
        sys.stdout, sys.stderr = old_stdout, old_stderr
        nd.PROGRESS_CALLBACK = None
        nd.ABORT_EVENT.clear()


def cancel() -> None:
    """実行中のダウンロードに中止を要求する（別スレッドから呼んでよい）。"""
    nd.ABORT_EVENT.set()
