# Taoguba Archiver

A small, local-first Windows/macOS utility for archiving a few Taoguba articles explicitly selected by the user.

This repository is standalone. It has no dependency on StockVault, Obsidian or any private knowledge-base layout.

> Status: pre-alpha local-first application. Core archival, additive HTML/Markdown export and the
> local browser workspace are implemented.

## Current capabilities

- Open a dedicated Chrome Profile for manual Taoguba login.
- Fetch one or several explicit article URLs.
- Archive the original response, rendered DOM, main-body HTML and body images.
- Parse only the main post by default.
- Record provenance, hashes and completeness in `metadata.json`.
- Preserve failed/truncated responses without presenting them as complete articles.
- Generate HTML and Markdown independently or together.
- Run a local browser workspace without sending login data or exports to a remote server.
- Report item progress, cooperative cancellation and login-expiry recovery.

## Development setup

```powershell
python -m venv .venv
& .venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
```

On macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The current implementation uses an installed Google Chrome through Playwright's `chrome` channel.

## Browser workspace

```powershell
python -m taoguba_archiver.web
```

The command starts a service bound only to `127.0.0.1` and opens the workspace in your default
browser. The browser UI talks to the local process, which owns Playwright, the dedicated Chrome
Profile and exports. Use `scripts/run_web.bat` to start it on Windows without typing a command.

Choose an export directory, paste one explicit Taoguba article URL per line, select one or both
output formats, and start the archive. For the first login, choose “登录淘股吧”, finish in the
application-owned Chrome window, then confirm in the browser workspace.

## CLI 使用（中文）

激活虚拟环境后，使用 `taoguba-archiver` 命令：

```powershell
& .\.venv\Scripts\Activate.ps1
```

首次登录会打开独立的 Chrome Profile：

```powershell
taoguba-archiver --login
```

归档一篇文章：

```powershell
taoguba-archiver "https://www.tgb.cn/a/ARTICLE_ID"
```

归档多篇文章，或从列表文件读取：

```powershell
taoguba-archiver URL_1 URL_2 URL_3
taoguba-archiver --urls-file urls.txt
```

`urls.txt` 必须是 UTF-8 编码；每行一个 URL，空行和以 `#` 开头的行会被忽略。

指定输出目录、无界面运行，并额外解析楼主跟帖：

```powershell
taoguba-archiver `
  --output-dir .\my-exports `
  --headless `
  --include-author-replies `
  "https://www.tgb.cn/a/ARTICLE_ID"
```

默认仅导出 HTML。需要额外导出 Markdown 时，必须指定图片处理方式：

```powershell
taoguba-archiver --markdown --markdown-images relative URL
```

- `relative`：引用归档目录内的图片，推荐。
- `source`：引用原始图片 URL。
- `embed`：将图片内嵌为 data URI。

只输出 Markdown：

```powershell
taoguba-archiver --markdown --markdown-images relative --no-html URL
```

其他常用参数：

```text
--profile-dir PATH    指定独立 Chrome 登录数据目录
--timeout SECONDS     页面和资源超时，默认 45 秒
--settle-ms MS        页面加载后额外等待，默认 1500 ms
--help                查看帮助
```

导出默认写入当前目录的 `exports/`。每篇文章包含 `response.html`、`rendered.html`、
`metadata.json`、`images/`，以及按选项生成的 `article-body.html` 和 `article.md`。

## First login

```bash
taoguba-archiver --login
```

Complete login in the Chrome window, then return to the terminal and press Enter. The app-owned
Profile is stored in the platform-native application data directory and is shared with the browser
workspace.

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
`source`, and `embed`. The browser workspace defaults to `relative` when Markdown is enabled; the
CLI still requires `--markdown-images` explicitly.

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

CLI and browser-workspace smoke checks:

```bash
taoguba-archiver --help
taoguba-archiver-web --help
```

## Safety and scope

- Only user-supplied Taoguba URLs are accepted.
- Cookie and `Set-Cookie` values are not written to exports.
- The tool is intended for personal, low-frequency archival use.
- Users are responsible for complying with site terms, copyright and applicable laws.

## License

No open-source license has been selected yet. Choose one before public GitHub release.
