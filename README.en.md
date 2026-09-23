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

Windows GUI (`novel_downloader_gui.py`): use the **Japanese / English** control in the top-right corner. The choice is stored in the GUI settings file. The inbox and bookshelf added in v2.14.0 are translated too.

`--lang` / `NOVEL_DOWNLOADER_LANG` select the UI language. `LANG` / `LC_ALL` are ignored so an English locale does not change the Japanese default.

## Supported sites

The engine still targets Japanese posting sites (Syosetu / Narou, Kakuyomu, Alphapolis, Estar, Hameln, Novema, Novelup+, and others listed in the Japanese README). Pass the work URL; the site is detected automatically. Single-episode Narou works, which have no table-of-contents page, are handled as of v2.14.0.

## Desktop GUI

`novel_downloader_gui.py` (requires `pip install customtkinter`) wraps the engine so it can be driven without a terminal. Two panels were added in v2.14.0:

- **Inbox** — watches a folder you share from your phone (OneDrive, Google Drive, a network share). It pulls every URL out of the dropped text files, expands short links, and shows the title, author and episode count *before* you download, so you can decide once you remember what the work was. Files that downloaded successfully move to `done\`; files with no URL are left alone. It rescans on launch, on a timer (5 minutes by default, 0 disables it), when the window regains focus, and on demand.
- **Bookshelf** — lists the `.txt` files in your output folder, checks them all for new episodes, and appends the ones that have any. There is no separate database; the `底本URL：` header line in each `.txt` is the index.

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
