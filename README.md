# Taoguba Archiver

A small, local-first Windows/macOS utility for archiving a few Taoguba articles explicitly selected by the user.

This repository is standalone. It has no dependency on StockVault, Obsidian or any private knowledge-base layout.

> [!IMPORTANT]
> **重要声明：本项目仅供个人学习、研究和技术交流使用。** 本项目不是淘股吧内容的权利人，
> 也不授予用户对淘股吧文章、图片或其他内容的任何版权或传播许可。
>
> - 用户仅应处理自己有权访问、复制和保存的内容，并自行遵守淘股吧的服务规则、著作权法及其他适用法律。
> - 未经权利人许可或法律明确允许，请勿将通过本项目获得的内容向公众发布、传播、出售、再分发或用于商业用途。
> - 用户应对其输入、归档、使用和传播的内容及由此产生的后果自行负责；项目作者不为用户的违规使用提供授权或背书。
>
> 本声明不构成法律意见，也不排除适用法律规定的责任。若对具体使用场景存在疑问，请先取得权利人许可或咨询专业人士。
>
> **Important notice: This project is provided solely for personal learning, research, and technical exchange.**
> The project is not the rights holder of Taoguba content and does not grant users any copyright or permission to distribute
> Taoguba articles, images, or other content.
>
> - Users must process only content they are entitled to access, copy, and retain, and must comply with Taoguba's terms of
>   service, copyright law, and all other applicable laws.
> - Unless the rights holder has granted permission or the law expressly allows it, do not publicly publish, distribute, sell,
>   redistribute, or use commercially any content obtained through this project.
> - Users are solely responsible for the content they submit, archive, use, or distribute, and for all resulting consequences.
>   The project authors do not authorize or endorse any non-compliant use.
>
> This notice is not legal advice and does not exclude any liability imposed by applicable law. If you are uncertain about a
> specific use, obtain permission from the rights holder or consult a qualified professional first.

> Status: pre-alpha local-first application. Core archival, additive HTML/Markdown export and the
> local browser workspace are implemented.

## Current capabilities

- Open a dedicated Chrome Profile for manual Taoguba login.
- Fetch one or several explicit article URLs.
- Create a standalone daily HTML reading page from one explicitly supplied personal “latest replies” URL.
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

The workspace also accepts one explicit personal “最新跟帖” page URL and a calendar date. It stops
pagination once it reaches older entries, filters strictly by each reply's timestamp, and creates a
separate `daily-replies.html`. It keeps target replies and their direct context; when Taoguba turns a
quoted image into `［图片］`, it looks only through the same source article's comment pages to recover
that image.

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

整理某位用户指定日期的最新跟帖：

```powershell
taoguba-archiver `
  --reply-feed "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396" `
  --reply-date 2026-07-21
```

该模式只处理你明确提供的“最新跟帖”页；会自动翻页到早于目标日期的位置，严格按每条跟帖的
时间过滤，并生成独立的 `daily-replies.html`、`metadata.json` 和本地 `images/`。它不会搜索或遍历
其他用户页面，也不会收集整篇文章的普通讨论。为避免重复打开同一篇主帖，它按主帖及评论分页
缓存页面；仅在引用显示为 `［图片］` 时，才在这篇主帖的已有分页中回溯原评论图片。最新跟帖模式
需要有界面 Chrome（淘股吧会拒绝无界面请求）。若页面响应异常、登录失效或有目标跟帖未定位到，
仍会保留 `response.html`、`rendered.html` 和 `metadata.json`，并标记为不完整。

归档一条明确提供的淘股吧说说：

```powershell
taoguba-archiver --shuo "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"
```

说说模式只接受这一条明确输入的说说 URL，不会把它与文章 URL、最新跟帖整理或批量 URL 文件混用。
该模式需要有界面 Chrome，固定生成以下五类归档产物：`response.html`、`rendered.html`、`shuo.html`、
`metadata.json` 和 `images/`。如果响应异常、登录失效或未解析到正文，仍会保留这些诊断产物并标记为不完整。

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
- A latest-replies export accepts only an explicitly supplied
  `/user/blog/moreReplyMod?userID=…` URL and stops at the requested date boundary.
- Cookie and `Set-Cookie` values are not written to exports.
- The tool is intended for personal, low-frequency archival use.
- Users are responsible for complying with site terms, copyright and applicable laws.

## License

This project is licensed under the [MIT License](LICENSE).
