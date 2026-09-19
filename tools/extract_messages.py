#!/usr/bin/env python3
"""novel_downloader.py から日本語を含むユーザー向け出力を洗い出す。

design_i18n.md §1 の数値を再現するための調査スクリプト。
print() / sys.stderr.write() / ロガー呼び出しを AST で全走査し、
日本語リテラルを含むものを層別に集計する。

  python3 tools/extract_messages.py                # 集計サマリ
  python3 tools/extract_messages.py --list P0      # 該当層の文言を列挙
  python3 tools/extract_messages.py --json         # 生データを JSON で出力
"""
import argparse
import ast
import collections
import json
import re
import sys
from pathlib import Path

JA = re.compile(r'[぀-ゟ゠-ヿ一-鿿]')

# design_i18n.md §1.2 の層
_TIER_RULES = [
    ("P0", r'\[エラー\]|\[警告\]|^エラー|エラー:|⚠|失敗|できません|見つかりません|必要です|無効|不正|中止'),
    ("P2", r'✅|📖|ℹ|\[情報\]|\[\d/3\]|取得中|生成中|完了'),
]

# design_i18n.md §2.1 の定型ブロック
_BOILERPLATE = {
    "3段階進捗":       r'^\[\d/3\]',
    "作品情報ヘッダ":   r'^(タイトル|著者|作者|原題)\s*[:：]',
    "件数表示":         r'^(エピソード数|取得エピソード|チャプター数|総ページ数|総文字数|話数)',
    "出力完了":         r'^✅\s*(テキスト|ePub)出力完了',
    "ePub生成中":       r'^📖',
    "URL正規化":        r'^(\[情報\] .*正規化しました|指定URL|正規化後)',
    "resume/Step":      r'^\[(resume|Step \d)\]',
    "サイト判別":       r'^(サイト判別|作品トップ|作品情報取得)',
}


def _tier(text: str) -> str:
    for name, pat in _TIER_RULES:
        if re.search(pat, text):
            return name
    return "P3"


def _innermost_scopes(tree: ast.AST) -> dict:
    """行番号 → 最も内側の関数名。"""
    scopes = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                prev = scopes.get(ln)
                if prev is None or span < prev[1]:
                    scopes[ln] = (node.name, span)
    return scopes


def _literal_text(node: ast.AST) -> str:
    """ノード配下の文字列リテラルを連結する（f-string の変数部は {} に畳む）。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
        elif isinstance(n, ast.FormattedValue):
            out.append("{}")
    return " ".join(out).strip()


def _output_kind(call: ast.Call):
    f = call.func
    if isinstance(f, ast.Name) and f.id == "print":
        return "print"
    if isinstance(f, ast.Attribute):
        v = f.value
        if f.attr == "write" and isinstance(v, ast.Attribute) and v.attr in ("stderr", "stdout"):
            return "stderr" if v.attr == "stderr" else "stdout"
        if f.attr in ("warning", "error", "info"):
            return "log"
    return None


def collect(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    scopes = _innermost_scopes(tree)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _output_kind(node)
        if not kind:
            continue
        text = _literal_text(node)
        if not JA.search(text):
            continue
        rows.append({
            "line": node.lineno,
            "kind": kind,
            "func": scopes.get(node.lineno, ("<module>", 0))[0],
            "tier": _tier(text),
            "text": text,
        })
    rows.sort(key=lambda r: r["line"])
    return rows


def count_help_strings(path: Path) -> int:
    """_build_arg_parser() 内の日本語を含む help / description / epilog の数。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    n = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "_build_arg_parser"):
            continue
        for call in [c for c in ast.walk(node) if isinstance(c, ast.Call)]:
            for kw in call.keywords:
                if kw.arg in ("help", "description", "epilog"):
                    s = "".join(x.value for x in ast.walk(kw.value)
                                if isinstance(x, ast.Constant) and isinstance(x.value, str))
                    if JA.search(s):
                        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default=None,
                    help="走査対象（既定: リポジトリ直下の novel_downloader.py）")
    ap.add_argument("--list", metavar="TIER", choices=["P0", "P2", "P3"],
                    help="指定した層の文言を出現回数つきで列挙する")
    ap.add_argument("--json", action="store_true", help="生データを JSON で出力する")
    args = ap.parse_args()

    path = Path(args.source) if args.source else Path(__file__).resolve().parent.parent / "novel_downloader.py"
    if not path.exists():
        print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
        return 1

    rows = collect(path)
    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0

    uniq = collections.Counter(r["text"] for r in rows)
    if args.list:
        for text in sorted(t for t in uniq if _tier(t) == args.list):
            print(f"{uniq[text]:3}x  {text}")
        return 0

    print(f"走査対象: {path}")
    print(f"呼び出し箇所: {len(rows)}   ユニーク文言: {len(uniq)}   "
          f"1回のみ: {sum(1 for v in uniq.values() if v == 1)}")
    print(f"CLI ヘルプ（日本語を含む help/description/epilog）: {count_help_strings(path)}")

    print("\n=== 出力種別 ===")
    for k, v in collections.Counter(r["kind"] for r in rows).most_common():
        print(f"  {k:<8}{v:>5}")

    print("\n=== 層別（design_i18n.md §1.2）===")
    tu = collections.Counter(); tc = collections.Counter()
    for text, n in uniq.items():
        tu[_tier(text)] += 1
        tc[_tier(text)] += n
    print(f"  {'層':<6}{'ユニーク':>9}{'箇所':>7}")
    for t in sorted(tu):
        print(f"  {t:<6}{tu[t]:>9}{tc[t]:>7}")

    print("\n=== 定型ブロックの複製（design_i18n.md §2.1）===")
    bc = collections.Counter(); bu = collections.defaultdict(set); bf = collections.defaultdict(set)
    for r in rows:
        for name, pat in _BOILERPLATE.items():
            if re.match(pat, r["text"]):
                bc[name] += 1; bu[name].add(r["text"]); bf[name].add(r["func"])
                break
    print(f"  {'ブロック':<18}{'箇所':>5}{'関数数':>7}{'表記ゆれ':>9}")
    for name, n in bc.most_common():
        print(f"  {name:<18}{n:>5}{len(bf[name]):>7}{len(bu[name]):>9}")
    total = sum(bc.values())
    print(f"  {'小計':<18}{total:>5}          "
          f"（全 {len(rows)} 箇所の {total * 100 // len(rows)}%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
