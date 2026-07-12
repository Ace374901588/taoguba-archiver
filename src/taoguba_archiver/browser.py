from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .core import (
    allocate_archive_dir,
    article_key_from_url,
    parse_article,
    safe_filename,
    validate_article_url,
)
from .markdown import render_article_markdown


SAFE_RESPONSE_HEADERS = {
    "content-type",
    "etag",
    "last-modified",
    "content-language",
    "cache-control",
}


@dataclass(frozen=True)
class BrowserFetchResult:
    url: str
    archive_dir: Path
    complete: bool
    incomplete_reason: str | None = None
    login_required: bool = False


@dataclass(frozen=True)
class BrowserBatchResult:
    items: list[BrowserFetchResult]
    cancelled: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _asset_name(url: str, content_type: str | None, index: int) -> str:
    path_name = Path(urlparse(url).path).name
    stem = safe_filename(Path(path_name).stem or f"image-{index}", max_length=48)
    extension = Path(path_name).suffix.lower()
    if not extension and content_type:
        extension = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
    if extension not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".bmp"}:
        extension = ".bin"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{index:02d}-{stem}-{digest}{extension}"


def _render_offline_article_html(
    article_html: str,
    page_url: str,
    asset_manifest: list[dict],
    *,
    title: str,
    author: str | None,
    published_at: str | None,
    source_url: str,
) -> str:
    """Create a portable, responsive reading page with local article images."""
    assets = {
        record["source_url"]: str(record["local_file"]).replace("\\", "/")
        for record in asset_manifest
        if record.get("local_file")
    }
    soup = BeautifulSoup(article_html, "html.parser")
    for tag in soup.select("script, style, iframe, object, embed"):
        tag.decompose()
    for tag in soup.find_all(True):
        for attribute in list(tag.attrs):
            if attribute.lower().startswith("on"):
                tag.attrs.pop(attribute, None)
    for image in soup.select("img"):
        source = image.get("data-original") or image.get("data-src") or image.get("src")
        if source:
            local_file = assets.get(urljoin(page_url, str(source)))
            if local_file:
                image["src"] = local_file
        for attribute in ("data-original", "data-src", "src2", "onclick", "onload"):
            image.attrs.pop(attribute, None)
        classes = [css_class for css_class in image.get("class", []) if css_class != "lazy"]
        if classes:
            image["class"] = classes
        else:
            image.attrs.pop("class", None)
        image["loading"] = "lazy"
        image["decoding"] = "async"

    details = []
    if author:
        details.append(f'<span>作者：{escape(author)}</span>')
    if published_at:
        details.append(f'<span>发布时间：{escape(published_at)}</span>')
    details_markup = "".join(details) or "<span>淘股吧文章归档</span>"
    safe_title = escape(title)
    safe_source_url = escape(source_url, quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title} · 淘股吧文章归档器</title>
<style>
:root{{color-scheme:light;--page:#f4f7fb;--surface:#ffffff;--ink:#172033;--muted:#64748b;--line:#e2e8f0;--brand:#0f766e;--quote:#f0fdfa}}
*{{box-sizing:border-box}}html{{background:var(--page)}}body{{margin:0;background:var(--page);color:var(--ink);font:16px/1.8 ui-sans-serif,system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;text-rendering:optimizeLegibility}}
.skip-link{{position:absolute;left:-9999px;top:12px;padding:8px 12px;background:#fff;color:var(--brand);border-radius:8px;z-index:1}}.skip-link:focus{{left:12px;outline:3px solid #5eead4}}
.archive-page{{width:min(100% - 32px,900px);margin:40px auto 64px}}.archive-header,.archive-article{{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:0 12px 32px rgba(15,23,42,.06)}}
.archive-header{{padding:32px 40px 28px;border-top:4px solid var(--brand)}}.archive-kicker{{margin:0 0 12px;color:var(--brand);font-size:13px;font-weight:700;letter-spacing:.08em}}h1{{margin:0;color:#0f172a;font-size:clamp(26px,4vw,36px);line-height:1.28;letter-spacing:-.02em}}
.archive-meta{{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:18px;color:var(--muted);font-size:14px}}.archive-meta span{{white-space:nowrap}}.archive-source{{display:inline-flex;margin-top:18px;color:var(--brand);font-size:14px;font-weight:650;text-decoration:none}}.archive-source:hover{{text-decoration:underline}}.archive-source:focus-visible{{outline:3px solid #5eead4;outline-offset:3px;border-radius:3px}}
.archive-article{{margin-top:18px;padding:36px 40px;overflow-wrap:anywhere}}.archive-article>:first-child{{margin-top:0}}.archive-article>:last-child{{margin-bottom:0}}.archive-article p{{margin:0 0 1.25em}}.archive-article h2,.archive-article h3,.archive-article h4{{margin:1.8em 0 .7em;line-height:1.4;color:#0f172a}}.archive-article h2{{font-size:1.45em}}.archive-article h3{{font-size:1.22em}}.archive-article a{{color:#0f766e;text-decoration-thickness:1px;text-underline-offset:3px}}.archive-article img{{display:block;max-width:100%;height:auto;margin:20px auto;border-radius:10px;box-shadow:0 3px 14px rgba(15,23,42,.1)}}.archive-article blockquote{{margin:1.4em 0;padding:12px 18px;border-left:4px solid #2dd4bf;background:var(--quote);color:#334155}}.archive-article pre{{max-width:100%;overflow:auto;padding:16px;border-radius:10px;background:#0f172a;color:#e2e8f0;font:14px/1.6 ui-monospace,"Cascadia Mono",Consolas,monospace}}.archive-article table{{display:block;max-width:100%;overflow:auto;border-collapse:collapse;margin:1.5em 0}}.archive-article th,.archive-article td{{padding:8px 12px;border:1px solid var(--line);text-align:left}}.archive-article th{{background:#f8fafc}}
.archive-footer{{margin:18px 0 0;color:var(--muted);font-size:13px;text-align:center}}@media (max-width: 640px){{body{{font-size:16px;line-height:1.75}}.archive-page{{width:min(100% - 20px,900px);margin:12px auto 32px}}.archive-header,.archive-article{{border-radius:12px}}.archive-header{{padding:24px 20px 22px}}.archive-article{{margin-top:12px;padding:24px 20px}}.archive-article img{{margin:16px auto;border-radius:8px}}}}
@media print{{html,body{{background:#fff}}.archive-page{{width:auto;margin:0}}.archive-header,.archive-article{{border:0;box-shadow:none}}.archive-source,.archive-footer{{display:none}}}}
</style>
</head>
<body>
<a class="skip-link" href="#article-content">跳到正文</a>
<main class="archive-page">
<header class="archive-header">
<p class="archive-kicker">淘股吧文章归档</p>
<h1>{safe_title}</h1>
<div class="archive-meta">{details_markup}</div>
<a class="archive-source" href="{safe_source_url}" target="_blank" rel="noreferrer">查看原文</a>
</header>
<article id="article-content" class="archive-article">{soup}</article>
<footer class="archive-footer">由淘股吧文章归档器生成 · 图片已保存至本地 images 目录</footer>
</main>
</body>
</html>
"""


class TaogubaBrowser:
    def __init__(
        self,
        profile_dir: Path,
        output_dir: Path,
        *,
        headless: bool = False,
        include_author_replies: bool = False,
        export_html: bool = True,
        export_markdown: bool = False,
        markdown_image_mode: str | None = None,
        timeout_ms: int = 45_000,
        settle_ms: int = 1_500,
    ) -> None:
        self.profile_dir = profile_dir.expanduser().resolve()
        self.output_dir = output_dir.resolve()
        self.headless = headless
        self.include_author_replies = include_author_replies
        self.export_html = export_html
        self.export_markdown = export_markdown
        self.markdown_image_mode = markdown_image_mode
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms

    def _launch(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "缺少 Playwright，请先执行：python -m pip install -r tools/taoguba_fetcher/requirements.txt"
            ) from exc

        manager = sync_playwright().start()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            context = manager.chromium.launch_persistent_context(
                str(self.profile_dir),
                channel="chrome",
                headless=self.headless,
                viewport={"width": 1440, "height": 1000},
            )
        except Exception:
            manager.stop()
            raise
        context.set_default_timeout(self.timeout_ms)
        return manager, context

    def login(self, wait_for_confirmation=None) -> None:
        manager, context = self._launch()
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.tgb.cn/", wait_until="domcontentloaded", timeout=self.timeout_ms)
            if wait_for_confirmation is None:
                print("请在打开的 Chrome 窗口中完成淘股吧登录。")
                input("确认页面已处于登录状态后，回到终端按 Enter 保存并退出……")
            else:
                wait_for_confirmation()
        finally:
            context.close()
            manager.stop()

    def fetch_many(
        self,
        urls: list[str],
        *,
        on_item_complete=None,
        should_cancel=None,
    ) -> BrowserBatchResult:
        normalized = [validate_article_url(url) for url in urls]
        manager, context = self._launch()
        items: list[BrowserFetchResult] = []
        cancelled = False
        try:
            page = context.pages[0] if context.pages else context.new_page()
            for index, url in enumerate(normalized, 1):
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
                archive_dir, complete, incomplete_reason, login_required = self._fetch_one(
                    context, page, url
                )
                item = BrowserFetchResult(
                    url=url,
                    archive_dir=archive_dir,
                    complete=complete,
                    incomplete_reason=incomplete_reason,
                    login_required=login_required,
                )
                items.append(item)
                if on_item_complete is not None:
                    on_item_complete(item, index, len(normalized))
        finally:
            context.close()
            manager.stop()
        return BrowserBatchResult(items=items, cancelled=cancelled)

    def _fetch_one(self, context, page, url: str) -> tuple[Path, bool, str | None, bool]:
        fetched_at = datetime.now().astimezone()
        response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        try:
            page.wait_for_selector(
                "#first, .article-text.p_coten", timeout=min(self.timeout_ms, 10_000)
            )
        except Exception:
            pass
        if self.settle_ms:
            page.wait_for_timeout(self.settle_ms)

        rendered_html = page.content()
        article = parse_article(
            rendered_html,
            page.url,
            include_author_replies=self.include_author_replies,
        )
        try:
            raw_bytes = response.body() if response is not None else b""
        except Exception:
            raw_bytes = b""
        status_code = response.status if response is not None else None
        response_headers = {
            key.lower(): value
            for key, value in (response.headers.items() if response is not None else [])
            if key.lower() in SAFE_RESPONSE_HEADERS
        }

        archive_dir = allocate_archive_dir(
            self.output_dir,
            article_key_from_url(url),
            article.title,
            fetched_at.strftime("%Y-%m-%d-%H%M%S"),
        )
        assets_dir = archive_dir / "images"
        assets_dir.mkdir(parents=True, exist_ok=False)
        (archive_dir / "response.html").write_bytes(raw_bytes)
        rendered_bytes = rendered_html.encode("utf-8")
        (archive_dir / "rendered.html").write_bytes(rendered_bytes)
        asset_manifest = []
        for index, image_url in enumerate(article.image_urls, 1):
            record = {"source_url": image_url, "local_file": None, "error": None}
            try:
                image_response = context.request.get(image_url, timeout=self.timeout_ms)
                if not image_response.ok:
                    raise RuntimeError(f"HTTP {image_response.status}")
                content_type = image_response.headers.get("content-type")
                image_bytes = image_response.body()
                filename = _asset_name(image_url, content_type, index)
                (assets_dir / filename).write_bytes(image_bytes)
                record.update(
                    local_file=f"images/{filename}",
                    content_type=content_type,
                    size=len(image_bytes),
                    sha256=_sha256(image_bytes),
                )
            except Exception as exc:
                record["error"] = str(exc)
            asset_manifest.append(record)

        if self.export_html:
            offline_html = _render_offline_article_html(
                article.main_html,
                page.url,
                asset_manifest,
                title=article.title,
                author=article.author,
                published_at=article.published_at,
                source_url=page.url,
            )
            (archive_dir / "article-body.html").write_text(offline_html, encoding="utf-8")

        if self.export_markdown:
            markdown = render_article_markdown(
                article,
                page.url,
                asset_manifest,
                image_mode=self.markdown_image_mode,
                archive_dir=archive_dir,
            )
            (archive_dir / "article.md").write_text(markdown, encoding="utf-8")

        http_ok = status_code is not None and 200 <= status_code < 400
        complete = http_ok and bool(article.main_text) and not article.login_required
        if not http_ok:
            incomplete_reason = f"HTTP 状态异常：{status_code}"
        elif article.login_required:
            incomplete_reason = "页面提示登录后查看全文"
        else:
            incomplete_reason = "未找到正文或正文为空"

        article_metadata = asdict(article)
        if not self.include_author_replies:
            article_metadata.pop("author_replies", None)
        metadata = {
            "schema_version": 1,
            "source": "淘股吧",
            "source_url": url,
            "final_url": page.url,
            "fetched_at": fetched_at.isoformat(),
            "status": "complete" if complete else "incomplete",
            "incomplete_reason": incomplete_reason if not complete else None,
            "http_status": status_code,
            "response_headers": response_headers,
            "response_sha256": _sha256(raw_bytes),
            "rendered_sha256": _sha256(rendered_bytes),
            "article": article_metadata,
            "assets": asset_manifest,
            "exports": {
                "html": self.export_html,
                "markdown": self.export_markdown,
                "markdown_image_mode": self.markdown_image_mode if self.export_markdown else None,
            },
        }
        (archive_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return archive_dir, complete, metadata["incomplete_reason"], article.login_required
