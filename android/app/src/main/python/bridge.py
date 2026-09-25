"""Android アプリと novel_downloader.py の橋渡し層。

Kotlin 側からは Chaquopy 経由で detect() / run() / append() / check() /
check_url() / count() / cancel() を呼ぶ。detect() 以外は本体のグローバル
（stdout・PROGRESS_CALLBACK・_CHECK_UPDATE_MODE 等）を触るので、Kotlin 側の
PyBridge.engine ロックの内側で1つずつ呼ぶこと（design_history.md §11.6）。
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


def _emit_meta(url: str, listener) -> None:
    """展開後の URL からサイトを判定して listener.onMeta() へ渡す。

    Kotlin 側の detect() はオフライン即時判定のため、短縮URL（share.google 等）では
    サイトが分からない。実際の展開は本体 main() が実行時に行うので、その結果が
    アプリに戻らず履歴の配信元が空になる。ここで同じ展開を行って補う。

    expand_short_url() は既知の短縮ホストでなければ通信せずそのまま返すため、
    通常の URL では追加コストが無い。サイト名は補助情報なので失敗しても無視する。
    """
    on_meta = getattr(listener, "onMeta", None)
    if on_meta is None:
        return
    try:
        site = nd.detect_site(nd.expand_short_url(url))
        if site in nd._SITE_DISPATCH:
            on_meta(json.dumps({
                "schema": 1,
                "site": site,
                "display_name": nd._SITE_DISPATCH[site][0],
            }, ensure_ascii=False))
    except Exception:
        pass


def _cli_opts(opts: dict) -> list:
    """アプリの設定 → CLI 引数。run() と append() で共通（design_history.md §15.2）。"""
    argv = []
    for key, flag in (("horizontal", "--horizontal"),
                      ("kobo", "--kobo"),
                      ("use_site_cover", "--use-site-cover"),
                      ("no_inline_images", "--no-inline-images")):
        if opts.get(key):
            argv.append(flag)
    return argv


def _run_main(argv: list, listener, meta_url: str = "") -> int:
    """nd.main(argv) を listener つきで実行し終了コードを返す（0=成功 / 130=中止 / 他=エラー）。

    listener は Kotlin 側の DownloadListener:
      onLine(text)・onProgress(n, total)・onPhase(phase)・onMeta(json)
    """
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
        if meta_url:
            _emit_meta(meta_url, listener)
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


def run(url: str, options_json: str, listener) -> int:
    """ダウンロードを実行して終了コードを返す（0=成功 / 130=中止 / 他=エラー）。"""
    opts = json.loads(options_json or "{}")
    # URL は必ず "--" の後ろに置く。"--from-file=…" のような値が来ても
    # オプションとして解釈させない（2026-09-26 セキュリティレビュー #1）
    argv = ["--output-dir", opts["output_dir"], *_cli_opts(opts), "--", url]
    return _run_main(argv, listener, meta_url=url)


def append(txt_path: str, options_json: str, listener) -> str:
    """--append で新着だけを追記し {"code": int, "added": int} を JSON で返す。

    CLI の --append と同じ経路（main()）を通す。_append_one() は
    --no-inline-images を引き継がないため使わない（design_history.md §11.3）。
    出力は txt と同じディレクトリに txt の stem で作られる。新着が無ければ
    本体はファイルを書き換えず、.epub も作らない。
    """
    opts = json.loads(options_json or "{}")
    before = count(txt_path)
    code = _run_main(["--append", txt_path, *_cli_opts(opts)], listener)
    after = count(txt_path) if code == 0 else before
    return json.dumps({"code": code, "added": max(0, after - before)})


def count(txt_path: str) -> int:
    """.txt の節の数（＝取得済みの話数。サイトによっては章・ページ）。読めなければ 0。"""
    try:
        return len(nd._load_existing_txt(txt_path)[0])
    except Exception:
        return 0


def check(txt_path: str) -> str:
    """手元の .txt とサイトを比べて新着を調べる（ファイルは書き換えない）。

    _check_update_one の結果（status / existing / total / new / new_titles /
    title / error）をそのまま JSON で返す。本体が一覧を print するので捨てる。
    """
    nd.ABORT_EVENT.clear()
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            r = nd._check_update_one(txt_path, 1.5)
    except BaseException as e:   # SystemExit も含めて結果に畳む
        r = {"status": "error", "error": str(e) or type(e).__name__}
    return json.dumps(r, ensure_ascii=False)


def check_url(url: str) -> str:
    """.txt が無いとき用。サイト側の総数だけを調べる（status は "init"）。"""
    nd.ABORT_EVENT.clear()
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            r = nd._check_update_url(url, 0, 1.5)
    except BaseException as e:
        r = {"status": "error", "error": str(e) or type(e).__name__}
    return json.dumps(r, ensure_ascii=False)


def cancel() -> None:
    """実行中のダウンロードに中止を要求する（別スレッドから呼んでよい）。"""
    nd.ABORT_EVENT.set()
