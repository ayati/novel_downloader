#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel_health_check.py

novel_downloader の対応サイトが正常にスクレイピングできるかを定期確認するツール。
各サイトのテスト用URLに対して --dry-run を実行し、タイトル・話数が取得できるかを検証する。

使い方:
    python novel_health_check.py                    # 全サイトをチェック
    python novel_health_check.py --site narou       # 特定サイトのみ
    python novel_health_check.py --site narou estar # 複数サイト指定
    python novel_health_check.py --list-sites       # 設定済みサイト一覧表示
    python novel_health_check.py --update-url narou https://ncode.syosetu.com/nXXXX/
                                                    # テストURLを更新
    python novel_health_check.py --timeout 120      # タイムアウト秒数を変更（デフォルト: 90）
    python novel_health_check.py --delay 5          # サイト間待機秒数を変更（デフォルト: 3）
    python novel_health_check.py --log-dir /path    # ログ出力先を変更
    python novel_health_check.py --no-color         # カラー出力を無効化

終了コード:
    0 ... 全サイト成功（またはスキップ）
    1 ... 1件以上の失敗あり（要修正）
    2 ... 設定エラー
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── パス設定 ────────────────────────────────────────────────────────────────
_HERE          = Path(__file__).parent
_DOWNLOADER    = _HERE / "novel_downloader.py"
_URLS_CONFIG   = _HERE / "novel_health_check_urls.json"
_DEFAULT_LOGDIR = _HERE / "health_check_logs"

# ── カラーコード ─────────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

OK      = _c("32;1", "[ OK ]")
FAIL    = _c("31;1", "[FAIL]")
SKIP    = _c("33;1", "[SKIP]")
WARN    = _c("33",   "[WARN]")
NOTSET  = _c("90",   "[----]")

# ── ユーティリティ ────────────────────────────────────────────────────────────

def _color_enabled(enabled: bool):
    """カラー出力のオン/オフを切り替える。"""
    global _USE_COLOR, OK, FAIL, SKIP, WARN, NOTSET
    _USE_COLOR = enabled
    OK     = _c("32;1", "[ OK ]")
    FAIL   = _c("31;1", "[FAIL]")
    SKIP   = _c("33;1", "[SKIP]")
    WARN   = _c("33",   "[WARN]")
    NOTSET = _c("90",   "[----]")


def load_urls_config() -> dict:
    if not _URLS_CONFIG.exists():
        print(f"エラー: 設定ファイルが見つかりません: {_URLS_CONFIG}", file=sys.stderr)
        print("  novel_health_check_urls.json をスクリプトと同じディレクトリに配置してください。",
              file=sys.stderr)
        sys.exit(2)
    with open(_URLS_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def save_urls_config(config: dict):
    with open(_URLS_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"設定を保存しました: {_URLS_CONFIG}")


def is_playwright_available() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import playwright"],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def check_python_dep(module: str) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


# ── 成功判定 ──────────────────────────────────────────────────────────────────

_EPISODE_PATTERNS = [
    re.compile(r"総話数\s*[：:]\s*(\d+)"),            # なろう
    re.compile(r"(\d+)\s*話を取得します"),             # カクヨム / アルファポリス
    re.compile(r"(\d+)\s*話を検出"),                   # カクヨム fallback
    re.compile(r"章数\s*[：:]\s*(\d+)"),               # genpaku / hyuki
    re.compile(r"エピソード数[：:]\s*(\d+)"),          # monogatary / ネオページ / ソリスピア
                                                       # ノベマ！ / ノベルアップ＋ / ステキブンゲイ / NOVEL DAYS
    re.compile(r"チャプター数[：:]\s*(\d+)"),          # 野いちご
    re.compile(r"総ページ数\s*[：:]\s*(\d+)"),         # エブリスタ / berry's cafe
    re.compile(r"(\d+)\s*話のデータが見つかりました"), # 汎用
]

def _parse_output(stdout: str, returncode: int) -> dict:
    """
    --dry-run の出力を解析して結果辞書を返す。

    返り値キー:
      success (bool)    ... 成功かどうか
      title   (str)     ... 取得できたタイトル（空文字 = 不明）
      episodes (int)    ... 取得できた話数/章数（0 = 不明 or 未取得）
      dry_run_confirmed (bool) ... [dry-run] メッセージを確認できたか
    """
    result = {
        "success": False,
        "title":   "",
        "episodes": 0,
        "dry_run_confirmed": False,
    }

    if returncode != 0:
        return result

    # [dry-run] メッセージ確認 → スクレイピング成功の最終確認
    if "[dry-run]" in stdout:
        result["dry_run_confirmed"] = True
        result["success"] = True

    # タイトル抽出（複数フォーマットに対応）
    title_m = re.search(r"タイトル\s*[：:]\s*(.+)", stdout)
    if title_m:
        result["title"] = title_m.group(1).strip()
    else:
        # 青空文庫等でタイトルが取れない場合はファイル名をフォールバックに使用
        fn_m = re.search(r"ファイル名:\s*(\S+)", stdout)
        if fn_m:
            result["title"] = fn_m.group(1)

    # 話数/章数抽出
    for pat in _EPISODE_PATTERNS:
        m = pat.search(stdout)
        if m:
            result["episodes"] = int(m.group(1))
            break

    return result


# ── 1サイトのチェック実行 ─────────────────────────────────────────────────────

def run_site_check(site_id: str, site_cfg: dict, timeout: int, inter_delay: float,
                   retry: int = 1) -> dict:
    """
    1サイトのヘルスチェックを実行する。

    返り値:
      status  : "ok" | "fail" | "skip" | "notset" | "error"
      message : 表示用メッセージ
      title   : 取得できたタイトル
      episodes: 取得できた話数
      elapsed : 経過秒数
      stdout  : dry-run の標準出力
      stderr  : dry-run の標準エラー
      returncode: プロセス終了コード
    """
    name = site_cfg.get("name", site_id)
    url  = site_cfg.get("url", "").strip()

    # URL未設定
    if not url:
        return {
            "status":     "notset",
            "message":    "テストURL未設定（novel_health_check_urls.json を編集して設定してください）",
            "title":      "",
            "episodes":   0,
            "elapsed":    0.0,
            "stdout":     "",
            "stderr":     "",
            "returncode": -1,
        }

    # ハーメルン: playwright 必須
    if site_id == "hameln" and not is_playwright_available():
        return {
            "status":     "skip",
            "message":    "playwright 未インストール（pip install playwright && python -m playwright install chromium）",
            "title":      "",
            "episodes":   0,
            "elapsed":    0.0,
            "stdout":     "",
            "stderr":     "",
            "returncode": -1,
        }

    # requests/bs4 必須チェック（一括）
    needs_bs4 = site_id not in {"narou", "aozora"}
    if needs_bs4 and not check_python_dep("bs4"):
        return {
            "status":     "skip",
            "message":    "beautifulsoup4 未インストール（pip install requests beautifulsoup4）",
            "title":      "",
            "episodes":   0,
            "elapsed":    0.0,
            "stdout":     "",
            "stderr":     "",
            "returncode": -1,
        }

    cmd = [
        sys.executable, str(_DOWNLOADER),
        url,
        "--dry-run",
        "--no-epub",
        "--delay", "1.0",
    ]

    last_result = None
    for attempt in range(retry + 1):
        if attempt > 0:
            time.sleep(5)  # リトライ前に5秒待機
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(_HERE),
            )
            elapsed = time.monotonic() - t0
            parsed  = _parse_output(proc.stdout, proc.returncode)

            last_result = {
                "status":     "ok" if parsed["success"] else "fail",
                "message":    (
                    f"タイトル「{parsed['title']}」"
                    + (f" 話数: {parsed['episodes']}" if parsed["episodes"] else "")
                    if parsed["success"]
                    else _first_error_line(proc.stdout, proc.stderr)
                ),
                "title":      parsed["title"],
                "episodes":   parsed["episodes"],
                "elapsed":    round(elapsed, 1),
                "stdout":     proc.stdout,
                "stderr":     proc.stderr,
                "returncode": proc.returncode,
            }

            if last_result["status"] == "ok":
                return last_result  # 成功したら即返す

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - t0
            last_result = {
                "status":     "fail",
                "message":    f"タイムアウト（{timeout}秒）",
                "title":      "",
                "episodes":   0,
                "elapsed":    round(elapsed, 1),
                "stdout":     "",
                "stderr":     "",
                "returncode": -1,
            }
        except Exception as e:
            elapsed = time.monotonic() - t0
            last_result = {
                "status":     "error",
                "message":    f"実行エラー: {e}",
                "title":      "",
                "episodes":   0,
                "elapsed":    round(elapsed, 1),
                "stdout":     "",
                "stderr":     "",
                "returncode": -1,
            }

    return last_result


def _first_error_line(stdout: str, stderr: str) -> str:
    """出力の中から最初のエラー行を抽出する。"""
    for line in (stdout + "\n" + stderr).splitlines():
        line = line.strip()
        if line.startswith("エラー:") or line.startswith("Error"):
            return line[:120]
    # エラー行が見つからない場合は最後の非空行
    for line in reversed((stdout + "\n" + stderr).splitlines()):
        line = line.strip()
        if line:
            return line[:120]
    return "（出力なし）"


# ── レポート出力 ──────────────────────────────────────────────────────────────

def print_header(timestamp: str):
    width = 70
    print("=" * width)
    print(f"  novel_downloader サイト動作確認  {timestamp}")
    print("=" * width)


def print_site_result(name: str, result: dict):
    status  = result["status"]
    elapsed = result["elapsed"]
    msg     = result["message"]
    elapsed_str = f"({elapsed:.1f}s)" if elapsed > 0 else ""

    if status == "ok":
        tag = OK
    elif status == "fail":
        tag = FAIL
    elif status == "skip":
        tag = SKIP
    elif status == "notset":
        tag = NOTSET
    else:
        tag = FAIL

    name_col = f"{name:<14}"
    print(f"{tag} {name_col} {msg} {elapsed_str}")


def print_footer(results: dict, config: dict):
    width = 70
    print("-" * width)
    ok_sites    = [s for s, r in results.items() if r["status"] == "ok"]
    fail_sites  = [s for s, r in results.items() if r["status"] in ("fail", "error")]
    skip_sites  = [s for s, r in results.items() if r["status"] == "skip"]
    notset_sites= [s for s, r in results.items() if r["status"] == "notset"]

    total_tested = len(ok_sites) + len(fail_sites)
    print(f"  結果: {len(ok_sites)}/{total_tested} 成功", end="")
    if skip_sites:
        print(f"  {len(skip_sites)} スキップ", end="")
    if notset_sites:
        print(f"  {len(notset_sites)} 未設定", end="")
    print()

    if fail_sites:
        names = [config[s]["name"] for s in fail_sites if s in config]
        print()
        print(_c("31;1", f"  ⚠ 要修正: {', '.join(names)}"))
        print(_c("31",   "    novel_health_check_urls.json のURLが有効か確認し、"))
        print(_c("31",   "    novel_downloader.py の該当スクレイパーを修正してください。"))
    print("=" * width)


# ── ログ保存 ─────────────────────────────────────────────────────────────────

def save_log(log_dir: Path, timestamp_str: str, results: dict, config: dict):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"health_{timestamp_str}.json"

    log_data = {
        "timestamp": timestamp_str,
        "summary": {
            "ok":     [s for s, r in results.items() if r["status"] == "ok"],
            "fail":   [s for s, r in results.items() if r["status"] in ("fail", "error")],
            "skip":   [s for s, r in results.items() if r["status"] == "skip"],
            "notset": [s for s, r in results.items() if r["status"] == "notset"],
        },
        "sites": {
            site_id: {
                "name":       config.get(site_id, {}).get("name", site_id),
                "url":        config.get(site_id, {}).get("url", ""),
                "status":     r["status"],
                "message":    r["message"],
                "title":      r["title"],
                "episodes":   r["episodes"],
                "elapsed":    r["elapsed"],
                "returncode": r["returncode"],
                # stdout/stderrはサイズが大きくなりうるため失敗時のみ記録
                **({"stdout": r["stdout"][-3000:], "stderr": r["stderr"][-1000:]}
                   if r["status"] in ("fail", "error") else {}),
            }
            for site_id, r in results.items()
        }
    }

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    return log_path


def rotate_logs(log_dir: Path, keep: int = 30):
    """古いログを削除して最新 keep 件だけ残す。"""
    logs = sorted(log_dir.glob("health_*.json"))
    for old in logs[:-keep]:
        old.unlink()


# ── デスクトップ通知 ──────────────────────────────────────────────────────────

def notify_failure(fail_names: list[str]):
    """Linux の notify-send でデスクトップ通知を送る（利用可能な場合のみ）。"""
    if not shutil.which("notify-send"):
        return
    body = "要修正サイト: " + ", ".join(fail_names)
    try:
        subprocess.run(
            ["notify-send", "-u", "critical",
             "novel_downloader 動作確認: 異常あり", body],
            timeout=5, check=False
        )
    except Exception:
        pass


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="novel_downloader 対応サイトの動作確認ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python novel_health_check.py                    # 全サイトチェック\n"
            "  python novel_health_check.py --site narou estar # 特定サイトのみ\n"
            "  python novel_health_check.py --list-sites       # サイト一覧と設定状況\n"
            "  python novel_health_check.py --update-url kakuyomu https://kakuyomu.jp/works/XXXX\n"
        )
    )
    parser.add_argument(
        "--site", nargs="+", metavar="SITE_ID",
        help="チェック対象サイトIDを指定（複数可）。省略時は全サイト",
    )
    parser.add_argument(
        "--list-sites", action="store_true",
        help="設定済みサイト一覧を表示して終了",
    )
    parser.add_argument(
        "--update-url", nargs=2, metavar=("SITE_ID", "URL"),
        help="指定サイトのテストURLを更新して保存",
    )
    parser.add_argument(
        "--timeout", type=int, default=90, metavar="SEC",
        help="1サイトあたりのタイムアウト秒数（デフォルト: 90）",
    )
    parser.add_argument(
        "--delay", type=float, default=3.0, metavar="SEC",
        help="サイト間の待機秒数（デフォルト: 3.0）",
    )
    parser.add_argument(
        "--retry", type=int, default=1, metavar="N",
        help="失敗時のリトライ回数（デフォルト: 1）",
    )
    parser.add_argument(
        "--log-dir", default=str(_DEFAULT_LOGDIR), metavar="DIR",
        help=f"ログ出力先ディレクトリ（デフォルト: {_DEFAULT_LOGDIR}）",
    )
    parser.add_argument(
        "--keep-logs", type=int, default=30, metavar="N",
        help="保持するログファイル数（デフォルト: 30）",
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="カラー出力を無効化",
    )
    parser.add_argument(
        "--no-notify", action="store_true",
        help="デスクトップ通知を無効化",
    )

    args = parser.parse_args()

    if args.no_color:
        _color_enabled(False)

    # novel_downloader.py の存在確認
    if not _DOWNLOADER.exists():
        print(f"エラー: novel_downloader.py が見つかりません: {_DOWNLOADER}", file=sys.stderr)
        sys.exit(2)

    config = load_urls_config()
    # _comment キーを除いた実サイト設定
    site_config = {k: v for k, v in config.items() if not k.startswith("_")}

    # ── --list-sites ─────────────────────────────────────────────────────────
    if args.list_sites:
        print(f"{'サイトID':<16} {'サイト名':<18} {'URL設定'}")
        print("-" * 70)
        for sid, scfg in site_config.items():
            url = scfg.get("url", "").strip()
            url_disp = url[:45] + "…" if len(url) > 46 else (url or _c("90", "（未設定）"))
            print(f"{sid:<16} {scfg.get('name',''):<18} {url_disp}")
        return

    # ── --update-url ──────────────────────────────────────────────────────────
    if args.update_url:
        sid, new_url = args.update_url
        if sid not in site_config:
            print(f"エラー: サイトID '{sid}' が見つかりません。"
                  f"--list-sites で有効なIDを確認してください。", file=sys.stderr)
            sys.exit(2)
        config[sid]["url"] = new_url
        save_urls_config(config)
        return

    # ── チェック対象サイト決定 ─────────────────────────────────────────────────
    if args.site:
        unknown = [s for s in args.site if s not in site_config]
        if unknown:
            print(f"エラー: 不明なサイトID: {unknown}。--list-sites で確認してください。",
                  file=sys.stderr)
            sys.exit(2)
        target_sites = [(sid, site_config[sid]) for sid in args.site]
    else:
        target_sites = list(site_config.items())

    # ── ヘッダー ───────────────────────────────────────────────────────────────
    now_dt = datetime.datetime.now()
    ts_display = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    ts_file    = now_dt.strftime("%Y%m%d_%H%M%S")
    print_header(ts_display)
    print(f"  チェック対象: {len(target_sites)} サイト  "
          f"タイムアウト: {args.timeout}s  サイト間待機: {args.delay}s")
    print()

    # ── 各サイトのチェック実行 ─────────────────────────────────────────────────
    results = {}
    for i, (sid, scfg) in enumerate(target_sites):
        if i > 0:
            time.sleep(args.delay)

        name = scfg.get("name", sid)
        print(f"  確認中: {name}…", end="", flush=True)

        result = run_site_check(sid, scfg, args.timeout, args.delay, retry=args.retry)
        results[sid] = result

        # 行頭に戻って結果行を上書き
        print(f"\r", end="")
        print_site_result(name, result)

    # ── フッター・集計 ─────────────────────────────────────────────────────────
    print()
    print_footer(results, site_config)

    # ── ログ保存 ───────────────────────────────────────────────────────────────
    log_dir = Path(args.log_dir)
    log_path = save_log(log_dir, ts_file, results, site_config)
    rotate_logs(log_dir, keep=args.keep_logs)
    print(f"\n  ログ: {log_path}")

    # ── 失敗時の通知・終了コード ───────────────────────────────────────────────
    fail_sites = [sid for sid, r in results.items() if r["status"] in ("fail", "error")]
    if fail_sites and not args.no_notify:
        fail_names = [site_config[s]["name"] for s in fail_sites if s in site_config]
        notify_failure(fail_names)

    sys.exit(1 if fail_sites else 0)


if __name__ == "__main__":
    main()
