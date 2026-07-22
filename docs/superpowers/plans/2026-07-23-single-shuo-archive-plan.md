# 单条淘股吧说说归档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为一条明确输入的淘股吧说说 URL 生成带本地图片的便携 HTML 导出包。

**Architecture:** 新建 `shuo.py`，隔离 URL 校验、页面解析与 HTML 渲染；`browser.py` 只负责单页获取、安全诊断与资产下载。服务、CLI 和网页工作台共用一个单条归档入口。

**Tech Stack:** Python 3.10+、BeautifulSoup、Playwright、unittest、Ruff。

## Global Constraints

- 只接受用户提供的 HTTPS `shuo.tgb.cn/shuo/toViewShuo?shuoID=<数字>` URL。
- 不发现、遍历或批量抓取说说、用户、评论和转发链。
- 不导出 Cookie、令牌、`Set-Cookie` 或 Profile 内容。
- 输出固定为 `shuo.html`、`images/`、`metadata.json`、`response.html`、`rendered.html`。
- 复用独立 Chrome Profile 和后台 Playwright 生命周期；说说模式拒绝无界面运行。
- 使用 `Path`，不硬编码盘符、Chrome 路径或系统字体。

---

### Task 1: 独立说说解析器

**Files:** Create `src/taoguba_archiver/shuo.py`; create `tests/test_shuo.py`.

**Interfaces:** Define frozen `ShuoContent(title: str, author: str | None, published_at: str | None, body_text: str, body_html: str, image_urls: list[str], login_required: bool)`. Define `validate_shuo_url(url: str) -> str`, `parse_shuo(html: str, page_url: str) -> ShuoContent`, and `render_shuo_html(content: ShuoContent, local_images: dict[str, str], source_url: str) -> str`.

- [ ] **Step 1: Write failing tests.** Add a fixture with title, author, time, body, a `data-original` content image, a placeholder image, a `css.tgb.cn` face image, and an executable attribute. Assert that a valid numeric `shuoID` is accepted; other host/path/non-numeric ID is rejected; parsing extracts title/author/time/body and only the content image; rendering uses `images/01.png` and omits `data-original`/`onclick`.
- [ ] **Step 2: Run RED.** Run `./.venv/Scripts/python.exe -m unittest tests.test_shuo -v`. Expected: import error for `taoguba_archiver.shuo`.
- [ ] **Step 3: Implement minimum parser.** Parse only a fixture-verified ordered selector set for title, author, time and body. Resolve images in `data-original`, `data-src`, `src2`, `src` order; reject data URIs, placeholders and `css.tgb.cn` UI assets. Sanitize script/style/iframe/embed and `on*` attributes; rewrite only downloaded images to local relative paths.
- [ ] **Step 4: Run GREEN.** Run `./.venv/Scripts/python.exe -m unittest tests.test_shuo -v`. Expected: all tests pass.
- [ ] **Step 5: Commit.** Run `git add src/taoguba_archiver/shuo.py tests/test_shuo.py && git commit -m "feat: parse explicit taoguba shuo pages"`.

### Task 2: 浏览器归档、诊断与完整性

**Files:** Modify `src/taoguba_archiver/browser.py`; modify `tests/test_browser_export.py`.

**Interfaces:** Define `ShuoFetchResult(url: str, archive_dir: Path, complete: bool, incomplete_reason: str | None = None, login_required: bool = False)`. Define `TaogubaBrowser.fetch_shuo(shuo_url: str) -> ShuoFetchResult`.

- [ ] **Step 1: Write failing tests.** Extend current fake page to return a `SHUO_HTML` fixture and safe response for `https://shuo.tgb.cn/...`. Assert `fetch_shuo` writes `shuo.html`, `response.html`, `rendered.html`, `images/`, and metadata with `source_type == "shuo"` and no `set-cookie`. Add a fake 502 response test asserting incomplete status and `HTTP 502` reason.
- [ ] **Step 2: Run RED.** Run `./.venv/Scripts/python.exe -m unittest tests.test_browser_export.BrowserExportTests.test_exports_one_shuo_with_diagnostics -v`. Expected: `fetch_shuo` attribute is absent.
- [ ] **Step 3: Implement minimum browser export.** Validate URL; reject `self.headless`; launch one page; retain raw response and rendered DOM; parse content; create `allocate_archive_dir(self.output_dir, "shuo", content.title, timestamp)`; download only parsed content images via `_asset_name`; emit `shuo.html`; build safe manifest records and metadata. Always retain diagnostics; mark incomplete for non-2xx/3xx, login marker, or empty body.
- [ ] **Step 4: Run GREEN.** Run `./.venv/Scripts/python.exe -m unittest tests.test_browser_export -v`. Expected: existing article/latest-reply tests plus new shuo success/failure tests pass.
- [ ] **Step 5: Commit.** Run `git add src/taoguba_archiver/browser.py tests/test_browser_export.py && git commit -m "feat: export explicit shuo pages"`.

### Task 3: 服务与命令行入口

**Files:** Modify `src/taoguba_archiver/service.py`; modify `src/taoguba_archiver/cli.py`; modify `tests/test_cli.py`; modify `README.md`.

**Interfaces:** Define `ArchiveService.archive_shuo(shuo_url: str, options: ArchiveOptions) -> ShuoFetchResult`. Add mutually-exclusive CLI option `--shuo URL`.

- [ ] **Step 1: Write failing tests.** Add `FakeService.archive_shuo`; assert `main(["--shuo", "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"]) == 0` and its URL reaches the fake. Assert `SystemExit` for `--headless --shuo`, for article URL plus `--shuo`, and for `--reply-feed` plus `--shuo`.
- [ ] **Step 2: Run RED.** Run `./.venv/Scripts/python.exe -m unittest tests.test_cli -v`. Expected: parser rejects unknown `--shuo`.
- [ ] **Step 3: Implement routing.** `archive_shuo` must construct the existing browser with `validate_exports=False` then call `fetch_shuo`. CLI must reject mixing `--shuo` with positional URLs, `--urls-file`, `--reply-feed`, `--headless`, `--markdown`, and `--no-html`; print the result directory; return `3` for incomplete output. Add README Chinese command example and five-artifact list.
- [ ] **Step 4: Run GREEN.** Run `./.venv/Scripts/python.exe -m unittest tests.test_cli -v; ./.venv/Scripts/python.exe -m taoguba_archiver --help`. Expected: tests pass and help contains `--shuo`.
- [ ] **Step 5: Commit.** Run `git add src/taoguba_archiver/service.py src/taoguba_archiver/cli.py tests/test_cli.py README.md && git commit -m "feat: add explicit shuo cli entry"`.

### Task 4: 网页工作台入口和回归

**Files:** Modify `src/taoguba_archiver/web.py`; modify `tests/test_web.py`.

**Interfaces:** Define `WebApp.start_shuo(shuo_url: str) -> dict`; define `_archive_shuo(shuo_url: str, options: ArchiveOptions) -> None`; expose `POST /api/shuo` with `shuo_url`.

- [ ] **Step 1: Write failing tests.** Extend the fake service with `archive_shuo`; call `start_shuo` then `wait_for_idle`; assert event text `开始归档说说` and `说说归档完成`. In local-server test assert `id="shuoUrl"` and `/api/shuo` exist.
- [ ] **Step 2: Run RED.** Run `./.venv/Scripts/python.exe -m unittest tests.test_web -v`. Expected: missing `start_shuo` and HTML/API route.
- [ ] **Step 3: Implement workspace action.** Add a dedicated “单条说说归档” URL input/button; send only `shuo_url` to `/api/shuo`; validate with `validate_shuo_url`; run `archive_shuo` in the existing worker pattern; log complete archive directory or safe incomplete reason; change login state only when `login_required` is true.
- [ ] **Step 4: Full verification and live regression.** Run `./.venv/Scripts/python.exe -m unittest discover -s tests -v`; `./.venv/Scripts/python.exe -m compileall -q src`; `./.venv/Scripts/python.exe -m ruff check src tests`; `git diff --check`; then `./.venv/Scripts/python.exe -m taoguba_archiver --shuo "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=2079570335635705862" --output-dir ./exports`. Expected: all checks exit 0 and the new archive holds the five artifacts without secrets.
- [ ] **Step 5: Commit.** Run `git add src/taoguba_archiver/web.py tests/test_web.py && git commit -m "feat: add explicit shuo workspace entry"`.

## Self-Review

- Spec coverage: Tasks 1–4 cover explicit URL scope, parser, content-only local images, diagnostics, incomplete states, CLI/workspace entry, documentation, tests, lint and live validation.
- Placeholder scan: no deferred implementation markers remain; DOM selectors must be verified from a non-sensitive fixture before production parsing.
- Type consistency: `ShuoContent` is consumed by `fetch_shuo`; `ShuoFetchResult` is returned by `archive_shuo`; CLI and web both consume that service method.
