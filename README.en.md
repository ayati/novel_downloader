# novel_downloader

[Japanese](README.md) | [English](README.en.md)

Command-line tool that downloads publicly posted Japanese web novels and writes **Aozora Bunko-style text** (`.txt`) plus **vertical-writing EPUB3** (`.epub`).

This English UI option is a contribution on top of [ayati/novel_downloader](https://github.com/ayati/novel_downloader). It changes help text and the desktop GUI language. It does **not** translate the novel body.

## English option

```bash
# English help
python novel_downloader.py --lang en --help

# Persistent default for the current shell
export NOVEL_DOWNLOADER_LANG=en
python novel_downloader.py --help
```

Windows GUI (`novel_downloader_gui.py`): use the **Japanese / English** control in the top-right corner. The choice is stored in the GUI settings file.

`--lang` / `NOVEL_DOWNLOADER_LANG` select the UI language. `LANG` / `LC_ALL` are ignored so an English locale does not change the Japanese default.

## Supported sites

The engine still targets Japanese posting sites (Syosetu / Narou, Kakuyomu, Alphapolis, Estar, Hameln, Novema, Novelup+, and others listed in the Japanese README). Pass the work URL; the site is detected automatically.

## Requirements

- Python 3.10+
- `pip install requests beautifulsoup4`
- Hameln additionally needs Playwright: `pip install playwright && python -m playwright install chromium`
- Optional JPEG covers: Pillow and a CJK font

## Basic usage

```bash
python novel_downloader.py https://ncode.syosetu.com/nXXXXxx/
python novel_downloader.py https://kakuyomu.jp/works/XXXXXXXXXX
python novel_downloader.py --from-file work.txt
python novel_downloader.py --from-epub work.epub
```

Output files are named from the work title:

```
Title.txt
Title.epub
Title.kepub.epub    # with --kobo
```

Please keep at least a 1-second gap between requests. Generated EPUBs include a link back to the source site.

See the [Japanese README](README.md) for the full option table, watch mode, cover rules, and Windows / Android packages.

## Licence

MIT License — Copyright (c) 2026 N. Aono
