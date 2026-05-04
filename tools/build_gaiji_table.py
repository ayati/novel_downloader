#!/usr/bin/env python3
"""
Build data/aozora_gaiji_jis0213.tsv from x0213.org's official mapping table.

Source : https://x0213.org/codetable/jisx0213-2004-std.txt
Output : data/aozora_gaiji_jis0213.tsv

Source format (tab-separated):
    {prefix}-{XXXX}\\tU+XXXX[+XXXX]\\t# description [\\tannotation]
    prefix=3 → JIS X 0213 plane 1 (第3水準)
    prefix=4 → JIS X 0213 plane 2 (第4水準)
    XXXX    → row+0x20 and cell+0x20 in 2-hex-digit pairs

Output format:
    {plane}-{row}-{cell}\\t{character}\\t{U+codepoint[+codepoint]}
    keyed exactly to match Aozora's "第3水準1-X-Y" / "第4水準2-X-Y" notation.

Usage:
    python tools/build_gaiji_table.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://x0213.org/codetable/jisx0213-2004-std.txt"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "aozora_gaiji_jis0213.tsv"


def parse_codepoints(field: str) -> str:
    """'U+304B+309A' → '304B+309A' (strip leading U+, keep + separator).

    Source format puts U+ only at the very start; '+' alone separates further
    codepoints in the rare combining-character entries.
    """
    return field[2:] if field.startswith("U+") else field


def codepoints_to_chars(codepoints: str) -> str:
    """'304B+309A' → 'か゛' (concatenate codepoints into a single grapheme)."""
    return "".join(chr(int(cp, 16)) for cp in codepoints.split("+"))


def parse_jis_key(key: str) -> tuple[int, int, int] | None:
    """'4-216F' → (plane=2, row=1, cell=79). prefix 3→plane 1, 4→plane 2."""
    if "-" not in key:
        return None
    prefix, hex4 = key.split("-", 1)
    if prefix not in ("3", "4") or len(hex4) != 4:
        return None
    plane = 1 if prefix == "3" else 2
    try:
        row  = int(hex4[0:2], 16) - 0x20
        cell = int(hex4[2:4], 16) - 0x20
    except ValueError:
        return None
    if not (1 <= row <= 94) or not (1 <= cell <= 94):
        return None
    return plane, row, cell


def main() -> int:
    print(f"Fetching {SOURCE_URL} ...", file=sys.stderr)
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as r:
        source = r.read().decode("ascii")

    rows: list[tuple[str, str, str]] = []
    skipped = 0
    for line in source.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        jis_key, ucs_field = cols[0].strip(), cols[1].strip()
        parsed = parse_jis_key(jis_key)
        if not parsed:
            skipped += 1
            continue
        plane, row, cell = parsed
        if not ucs_field.startswith("U+"):
            skipped += 1
            continue
        codepoints = parse_codepoints(ucs_field)
        try:
            char = codepoints_to_chars(codepoints)
        except (ValueError, OverflowError):
            skipped += 1
            continue
        aozora_key = f"{plane}-{row}-{cell}"
        rows.append((aozora_key, char, codepoints))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Aozora gaiji notation → Unicode mapping (JIS X 0213:2004)\n")
        f.write(f"# Source : {SOURCE_URL}\n")
        f.write("# License: free use/modify/distribute (Project X0213, 2009)\n")
        f.write("# Format : plane-row-cell<TAB>character<TAB>U+XXXX[+XXXX]\n")
        f.write("#   plane=1 → Aozora 第3水準1-X-Y\n")
        f.write("#   plane=2 → Aozora 第4水準2-X-Y\n")
        for key, char, cps in rows:
            f.write(f"{key}\t{char}\t{cps}\n")

    print(f"Wrote {len(rows)} entries to {OUTPUT_PATH}", file=sys.stderr)
    if skipped:
        print(f"Skipped {skipped} non-mappable lines", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
