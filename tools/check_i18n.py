#!/usr/bin/env python3
"""T() のメッセージカタログを検査する（design_i18n.md §5.3）。

キーがずれても **実行時は日本語にフォールバックするだけで例外にならない**ため、
未翻訳・孤児は静的に突き合わせないと気づけない。逆に .format() の引数が
msgid のプレースホルダと食い違うと実行時 KeyError になるので、これも検査する。

  python3 tools/check_i18n.py
  python3 tools/check_i18n.py --list-untranslated
"""
import argparse
import ast
import re
import sys
from pathlib import Path

DEFAULT_SRC = Path(__file__).resolve().parent.parent / "novel_downloader.py"

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:![sra])?(?::[^}]*)?\}")

# design_i18n.md §4: 翻訳してはいけない文字列（T() に渡ってはいけない）
PROTECTED = [
    ("✅ ePub出力完了", "GUI が完了検出に使う契約"),
    ("✅ テキスト出力完了", "出力完了の対で契約に準じる"),
    ("底本URL：", ".txt のパースキー"),
    ("【あらすじ】", ".txt のヘッダー境界"),
]


def _catalog(tree: ast.AST) -> dict:
    """_MESSAGES_EN の {日本語: 英語} を返す。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_MESSAGES_EN" for t in node.targets):
            continue
        out = {}
        for k, v in zip(node.value.keys, node.value.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                out[k.value] = v.value
        return out
    return {}


def _t_calls(tree: ast.AST) -> list:
    """[(行, msgid, .format に渡された kwargs 名の集合 or None)] を返す。

    ast.walk は幅優先なので T(...).format(...) の外側が内側の T(...) より先に
    現れる。1パスで対応付けようとすると必ず取りこぼすため、先に .format() の
    ラッパーを集めてから T() を走査する。
    """
    wrapped = {}   # id(T ノード) -> kwargs 名の集合
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Name)
                and node.func.value.func.id == "T"):
            wrapped[id(node.func.value)] = {kw.arg for kw in node.keywords if kw.arg}

    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "T":
            a = node.args[0] if node.args else None
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                calls.append([node.lineno, a.value, wrapped.get(id(node))])
    return calls


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default=None)
    ap.add_argument("--list-untranslated", action="store_true",
                    help="未翻訳の msgid を列挙する")
    args = ap.parse_args()

    path = Path(args.source) if args.source else DEFAULT_SRC
    if not path.exists():
        print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
        return 2

    tree = ast.parse(path.read_text(encoding="utf-8"))
    cat = _catalog(tree)
    calls = _t_calls(tree)
    used = {c[1] for c in calls}

    untranslated = sorted(used - set(cat))
    orphan = sorted(set(cat) - used)

    mismatch_ph = []   # 日英でプレースホルダが違う
    for ja, en in cat.items():
        if sorted(PLACEHOLDER.findall(ja)) != sorted(PLACEHOLDER.findall(en)):
            mismatch_ph.append(ja)

    mismatch_fmt = []  # .format の引数が msgid と食い違う（実行時 KeyError）
    for lineno, msgid, names in calls:
        need = set(PLACEHOLDER.findall(msgid))
        if names is None:
            if need:
                mismatch_fmt.append((lineno, msgid, need, set()))
        elif names != need:
            mismatch_fmt.append((lineno, msgid, need, names))

    # 本文中で保護対象に「言及」するのは正常（例: 「底本URL：」行を含むファイルを指定…）。
    # 危険なのは英訳側でその語が消えている＝訳してしまっている場合だけ。
    protected_hits = []
    for _lineno, msgid, _ in calls:
        for frag, why in PROTECTED:
            if frag in msgid and frag not in cat.get(msgid, msgid):
                protected_hits.append((_lineno, msgid, why))

    print(f"T() 呼び出し: {len(calls)}   msgid: {len(used)}   カタログ: {len(cat)} 件")
    ok = True
    if untranslated:
        ok = False
        print(f"\n⚠ 未翻訳（無言で日本語になる）: {len(untranslated)} 件")
        for m in untranslated[:20]:
            print(f"   - {m[:80]!r}")
    if orphan:
        ok = False
        print(f"\n⚠ 孤児エントリ（原文が変わった可能性）: {len(orphan)} 件")
        for m in orphan[:20]:
            print(f"   - {m[:80]!r}")
    if mismatch_ph:
        ok = False
        print(f"\n⚠ 日英でプレースホルダが不一致: {len(mismatch_ph)} 件")
        for m in mismatch_ph:
            print(f"   - {m[:60]!r}\n     ja={PLACEHOLDER.findall(m)} en={PLACEHOLDER.findall(cat[m])}")
    if mismatch_fmt:
        ok = False
        print(f"\n⚠ .format() の引数不一致（実行時 KeyError）: {len(mismatch_fmt)} 件")
        for ln, m, need, got in mismatch_fmt:
            print(f"   - 行{ln}: {m[:50]!r}\n     必要={sorted(need)} 実際={sorted(got)}")
    if protected_hits:
        ok = False
        print(f"\n⚠ 保護対象を T() に渡している: {len(protected_hits)} 件")
        for ln, m, why in protected_hits:
            print(f"   - 行{ln}: {why}: {m[:50]!r}")

    if args.list_untranslated:
        for m in untranslated:
            print(m)
        return 0
    if ok:
        print("\n✅ 未翻訳・孤児・プレースホルダ不一致・保護対象の混入はありません")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
