#!/usr/bin/env python3
"""Android の文字列リソースが日英で揃っているか検査する。

values-en にキーが無い場合、Android は values/ へフォールバックするため
**ビルドは通り、無言で日本語が表示される**（android/design_i18n.md §11）。
ビルドでは検出できないので、このスクリプトで突き合わせる。

  python3 tools/check_android_strings.py
"""
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "android/app/src/main/res"
FORMAT_ARG = re.compile(r"%\d+\$[sd]")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _names(text: str, tag: str) -> set:
    return set(re.findall(rf'<{tag} name="([^"]+)"', text))


def _format_args(text: str) -> dict:
    """<string> ごとの番号付き書式引数（%1$s 等）を返す。"""
    return {
        name: sorted(FORMAT_ARG.findall(body))
        for name, body in re.findall(r'<string name="([^"]+)">(.*?)</string>', text, re.S)
    }


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROOT
    base, en = root / "values/strings.xml", root / "values-en/strings.xml"
    for f in (base, en):
        if not f.exists():
            print(f"エラー: ファイルが見つかりません: {f}", file=sys.stderr)
            return 2

    ja_t, en_t = _read(base), _read(en)
    ja = _names(ja_t, "string") | _names(ja_t, "plurals")
    en_k = _names(en_t, "string") | _names(en_t, "plurals")

    missing = sorted(ja - en_k)
    orphan = sorted(en_k - ja)
    ja_a, en_a = _format_args(ja_t), _format_args(en_t)
    mismatch = sorted(k for k in ja_a if k in en_a and ja_a[k] != en_a[k])

    print(f"既定(ja): {len(ja)} キー / values-en: {len(en_k)} キー")
    ok = True
    for label, items in (
        ("英語未訳（無言で日本語になる）", missing),
        ("英語だけにある孤児キー", orphan),
        ("書式引数の不一致", mismatch),
    ):
        if items:
            ok = False
            print(f"\n⚠ {label}: {len(items)} 件")
            for k in items:
                detail = f"  ja={ja_a.get(k)} en={en_a.get(k)}" if k in mismatch else ""
                print(f"   - {k}{detail}")
    if ok:
        print("✅ 日英のキーと書式引数はすべて一致しています")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
