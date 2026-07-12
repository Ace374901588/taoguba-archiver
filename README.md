# Taoguba Archiver

A small, local-first Windows/macOS utility for archiving a few Taoguba articles explicitly selected by the user.

This repository is standalone. It has no dependency on StockVault, Obsidian or any private knowledge-base layout.

> Status: pre-alpha desktop application. Core archival, additive HTML/Markdown export and the
> PySide6 GUI are implemented; public release identity, signing and notarization are not finalized.

## Current capabilities

- Open a dedicated Chrome Profile for manual Taoguba login.
- Fetch one or several explicit article URLs.
- Archive the original response, rendered DOM, main-body HTML and body images.
- Parse only the main post by default.
- Record provenance, hashes and completeness in `metadata.json`.
- Preserve failed/truncated responses without presenting them as complete articles.
- Generate HTML and Markdown independently or together.
- Run the native PySide6 GUI without blocking its main thread.
- Report item progress, cooperative cancellation and login-expiry recovery.

## Development setup

```powershell
python -m venv .venv
& .venv/Scripts/Activate.ps1
python -m pip install -e ".[dev,gui]"
```

On macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,gui]"
```

The current implementation uses an installed Google Chrome through Playwright's `chrome` channel.

## Desktop GUI

```powershell
taoguba-archiver-gui
```

Choose an export directory, paste one explicit Taoguba article URL per line, select one or both
output formats, and start the archive. The dedicated Chrome login flow is available from the main
window. Application settings contain no cookies or tokens and are stored through platform-native
configuration directories.

## First login

```bash
taoguba-archiver --login
```

Complete login in the Chrome window, then return to the terminal and press Enter. The app-owned
Profile is stored in the platform-native application data directory and is shared with the GUI.

## Archive selected URLs

```bash
taoguba-archiver "https://www.tgb.cn/a/ARTICLE_ID"
```

Multiple explicit URLs:

```bash
taoguba-archiver URL_1 URL_2 URL_3
```

Or a UTF-8 text file with one URL per line:

```bash
taoguba-archiver --urls-file urls.txt
```

The default destination is `./exports`. Use `--output-dir` to choose another folder.

Add a Markdown copy while keeping HTML:

```bash
taoguba-archiver --markdown --markdown-images relative "https://www.tgb.cn/a/ARTICLE_ID"
```

Use `--no-html` with `--markdown` for Markdown-only article output. Traceability files
`response.html` and `rendered.html` are still preserved. Markdown image modes are `relative`,
`source`, and `embed`; no mode is silently selected.

## Output

```text
exports/
└── <timestamp>-<article-id>-<safe-title>/
    ├── response.html
    ├── rendered.html
    ├── article-body.html     # optional HTML output
    ├── article.md            # optional Markdown output
    ├── metadata.json
    └── images/
```

The versioned portable contract is documented in [docs/export-schema-v1.md](docs/export-schema-v1.md).

## Tests

```bash
python -m unittest discover -s tests -v
```

Source and packaged GUI smoke tests:

```bash
taoguba-archiver-gui --smoke-test
python scripts/build_app.py --clean
```

Install packaging dependencies first with `python -m pip install -e ".[build]"`. Builds are
platform-native: run the command on Windows for a Windows directory bundle and on macOS for a macOS
application bundle.

## GUI design

- [Design specification](gui_design/UI_SPEC.md)
- [Interactive prototype](gui_design/prototype/main-window.html)
- [Main-window rules](gui_design/design-system/taoguba-article-archiver/pages/main-window.md)

## Safety and scope

- Only user-supplied Taoguba URLs are accepted.
- Cookie and `Set-Cookie` values are not written to exports.
- The tool is intended for personal, low-frequency archival use.
- Users are responsible for complying with site terms, copyright and applicable laws.

## License

No open-source license has been selected yet. Choose one before public GitHub release.
