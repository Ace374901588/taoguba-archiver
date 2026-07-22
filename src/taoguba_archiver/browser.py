from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from .core import (
    allocate_archive_dir,
    article_key_from_url,
    parse_article,
    safe_filename,
    validate_article_url,
)
from .daily_replies import (
    DailyReplyDetail,
    is_content_image_url,
    parse_associated_reply,
    parse_latest_reply_feed,
    render_daily_replies_html,
    resolve_quote_image_placeholder,
    validate_reply_feed_url,
)
from .markdown import render_article_markdown
from .shuo import parse_shuo, render_shuo_html, validate_shuo_url


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


@dataclass(frozen=True)
class DailyReplyFetchResult:
    feed_url: str
    target_date: str
    archive_dir: Path
    complete: bool
    reply_count: int
    incomplete_reason: str | None = None
    login_required: bool = False


@dataclass(frozen=True)
class ShuoFetchResult:
    url: str
    archive_dir: Path
    complete: bool
    incomplete_reason: str | None = None
    login_required: bool = False


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


def _safe_response_headers(response) -> dict[str, str]:
    headers = getattr(response, "headers", {}) if response is not None else {}
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in SAFE_RESPONSE_HEADERS
    }


def _response_bytes(response) -> bytes:
    try:
        return response.body() if response is not None else b""
    except Exception:
        return b""


_SENSITIVE_ATTRIBUTE_MARKERS = (
    "auth",
    "cookie",
    "credential",
    "csrf",
    "nonce",
    "passwd",
    "password",
    "secret",
    "session",
    "token",
    "xsrf",
)
_DIAGNOSTIC_URL_ATTRIBUTES = {
    "action",
    "cite",
    "data-original",
    "data-src",
    "formaction",
    "href",
    "longdesc",
    "poster",
    "src",
    "src2",
    "xlink:href",
}
_DIAGNOSTIC_ABSOLUTE_URL = re.compile(r"https?://[^\s<>\"']+")


def _contains_sensitive_marker(value: object) -> bool:
    lowered = str(value).lower()
    return any(marker in lowered for marker in _SENSITIVE_ATTRIBUTE_MARKERS)


def _sanitize_diagnostic_url(value: object) -> str | None:
    candidate = str(value).strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() in {"data", "javascript"}:
        return None
    if parsed.username or parsed.password:
        hostname = parsed.hostname or ""
        try:
            port = f":{parsed.port}" if parsed.port is not None else ""
        except ValueError:
            return None
        parsed = parsed._replace(netloc=f"{hostname}{port}")
    return parsed._replace(query="", fragment="").geturl()


def _sanitize_urls_in_text(value: str) -> str:
    def sanitize(match: re.Match) -> str:
        return _sanitize_diagnostic_url(match.group(0)) or ""

    return _DIAGNOSTIC_ABSOLUTE_URL.sub(sanitize, value)


def _sanitize_diagnostic_html(html: str) -> str:
    """Remove executable and credential-bearing content from saved diagnostics."""
    soup = BeautifulSoup(html, "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in soup.select("script, style, iframe, object, embed"):
        tag.decompose()
    for tag in soup.find_all(True):
        tag_name = str(tag.name).lower()
        if tag_name == "meta":
            identity = " ".join(
                str(tag.get(attribute, ""))
                for attribute in ("name", "http-equiv", "property", "id")
            )
            if _contains_sensitive_marker(identity) or str(
                tag.get("http-equiv", "")
            ).lower() == "refresh":
                tag.decompose()
                continue
        if tag_name == "input":
            identity = " ".join(
                str(tag.get(attribute, ""))
                for attribute in ("name", "id", "type", "autocomplete")
            )
            if _contains_sensitive_marker(identity):
                tag.decompose()
                continue
            if str(tag.get("type", "")).lower() in {"hidden", "password"}:
                tag.attrs.pop("value", None)
        for attribute in list(tag.attrs):
            lowered = attribute.lower()
            if (
                lowered.startswith("on")
                or lowered == "style"
                or _contains_sensitive_marker(lowered)
            ):
                tag.attrs.pop(attribute, None)
                continue
            if lowered == "srcset":
                tag.attrs.pop(attribute, None)
                continue
            if lowered in _DIAGNOSTIC_URL_ATTRIBUTES:
                sanitized = _sanitize_diagnostic_url(tag.attrs[attribute])
                if sanitized:
                    tag.attrs[attribute] = sanitized
                else:
                    tag.attrs.pop(attribute, None)
    for text_node in soup.find_all(string=True):
        sanitized = _sanitize_urls_in_text(str(text_node))
        if sanitized != str(text_node):
            text_node.replace_with(sanitized)
    return str(soup)


def _is_expected_shuo_final_url(final_url: object, expected_url: str) -> bool:
    try:
        return validate_shuo_url(str(final_url)) == expected_url
    except (TypeError, ValueError):
        return False


def _same_image_origin_and_path(source_url: str, final_url: object) -> bool:
    try:
        source = urlparse(source_url)
        final = urlparse(str(final_url))
        source_port = source.port
        final_port = final.port
    except (TypeError, ValueError):
        return False
    if source.username or source.password or final.username or final.password:
        return False
    return (
        source.scheme.lower() in {"http", "https"}
        and source.scheme.lower() == final.scheme.lower()
        and (source.hostname or "").lower() == (final.hostname or "").lower()
        and source_port == final_port
        and source.path == final.path
    )


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
                "缺少 Playwright，请先执行：python -m pip install -e \".[dev]\""
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

    def fetch_shuo(self, shuo_url: str) -> ShuoFetchResult:
        """Export exactly one explicitly supplied shuo page and its body images."""
        normalized_url = validate_shuo_url(shuo_url)
        if self.headless:
            raise ValueError("说说导出需要使用可见浏览器窗口")

        manager, context = self._launch()
        try:
            page = context.pages[0] if context.pages else context.new_page()
            fetched_at = datetime.now().astimezone()
            response = None
            navigation_error = None
            final_url_in_scope = False
            rendered_html = ""
            try:
                response = page.goto(
                    normalized_url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )
                try:
                    page.wait_for_selector(
                        ".shuo-content", timeout=min(self.timeout_ms, 10_000)
                    )
                except Exception:
                    pass
                if self.settle_ms:
                    page.wait_for_timeout(self.settle_ms)
                final_url_in_scope = _is_expected_shuo_final_url(
                    getattr(page, "url", None), normalized_url
                )
                rendered_html = page.content()
            except Exception as exc:
                navigation_error = (
                    "页面导航失败（超时）"
                    if type(exc).__name__ == "TimeoutError"
                    else "页面导航失败"
                )

            raw_html = _response_bytes(response).decode("utf-8", errors="replace")
            safe_response_html = _sanitize_diagnostic_html(raw_html)
            safe_rendered_html = _sanitize_diagnostic_html(rendered_html)
            raw_bytes = safe_response_html.encode("utf-8")
            rendered_bytes = safe_rendered_html.encode("utf-8")
            status_code = getattr(response, "status", None)
            response_headers = _safe_response_headers(response)
            content = parse_shuo(
                safe_rendered_html if final_url_in_scope else "",
                normalized_url,
            )

            archive_dir = allocate_archive_dir(
                self.output_dir,
                "shuo",
                content.title,
                fetched_at.strftime("%Y-%m-%d-%H%M%S"),
            )
            assets_dir = archive_dir / "images"
            assets_dir.mkdir(parents=True, exist_ok=False)
            (archive_dir / "response.html").write_bytes(raw_bytes)
            (archive_dir / "rendered.html").write_bytes(rendered_bytes)

            local_images: dict[str, str] = {}
            asset_manifest = []
            for index, image_url in enumerate(content.image_urls, 1):
                record = {
                    "source_url": image_url,
                    "kind": "content",
                    "local_file": None,
                    "error": None,
                }
                try:
                    image_response = context.request.get(
                        image_url, timeout=self.timeout_ms
                    )
                    if not image_response.ok:
                        record["error"] = f"HTTP {image_response.status}"
                        asset_manifest.append(record)
                        continue
                    if not _same_image_origin_and_path(
                        image_url, getattr(image_response, "url", None)
                    ):
                        record["error"] = "图片响应 URL 超出允许范围"
                        asset_manifest.append(record)
                        continue
                    content_type = str(
                        image_response.headers.get("content-type", "")
                    ).split(";", 1)[0].strip().lower()
                    if not content_type.startswith("image/"):
                        record["error"] = "响应内容不是图片"
                        asset_manifest.append(record)
                        continue
                    image_bytes = image_response.body()
                    filename = _asset_name(image_url, content_type, index)
                    (assets_dir / filename).write_bytes(image_bytes)
                    local_file = f"images/{filename}"
                    local_images[image_url] = local_file
                    record.update(
                        local_file=local_file,
                        content_type=content_type,
                        size=len(image_bytes),
                        sha256=_sha256(image_bytes),
                    )
                except Exception:
                    record["error"] = "图片下载失败"
                asset_manifest.append(record)

            output_html = render_shuo_html(content, local_images, normalized_url)
            (archive_dir / "shuo.html").write_text(output_html, encoding="utf-8")

            reasons = []
            http_ok = status_code is not None and 200 <= status_code < 400
            if navigation_error:
                reasons.append(navigation_error)
            elif not final_url_in_scope:
                reasons.append("最终页面 URL 超出允许的说说范围")
            if navigation_error is None and not http_ok:
                reasons.append(f"HTTP {status_code if status_code is not None else '未知状态'}")
            if content.login_required:
                reasons.append("页面提示登录后查看全文")
            if not content.body_text:
                reasons.append("未找到说说正文或正文为空")
            incomplete_reason = "；".join(reasons) or None
            complete = incomplete_reason is None
            metadata = {
                "schema_version": 1,
                "source": "淘股吧",
                "source_type": "shuo",
                "source_url": normalized_url,
                "final_url": normalized_url if final_url_in_scope else None,
                "fetched_at": fetched_at.isoformat(),
                "status": "complete" if complete else "incomplete",
                "incomplete_reason": incomplete_reason,
                "http_status": status_code,
                "response_headers": response_headers,
                "response_sha256": _sha256(raw_bytes),
                "rendered_sha256": _sha256(rendered_bytes),
                "shuo": asdict(content),
                "assets": asset_manifest,
            }
            (archive_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return ShuoFetchResult(
                url=normalized_url,
                archive_dir=archive_dir,
                complete=complete,
                incomplete_reason=incomplete_reason,
                login_required=content.login_required,
            )
        finally:
            context.close()
            manager.stop()

    def fetch_latest_replies(self, feed_url: str, target_date: str) -> DailyReplyFetchResult:
        """Export one explicitly supplied user's latest replies for one calendar date.

        Pagination stops as soon as the feed reaches a date older than ``target_date``.
        It never follows profile links or discovers other users' pages.
        """
        normalized_feed_url = validate_reply_feed_url(feed_url)
        try:
            requested_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("日期必须是 YYYY-MM-DD，例如 2026-07-21") from exc

        manager, context = self._launch()
        try:
            page = context.pages[0] if context.pages else context.new_page()
            feed_response = page.goto(normalized_feed_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.settle_ms:
                page.wait_for_timeout(self.settle_ms)
            feed_raw = _response_bytes(feed_response)
            feed_status = getattr(feed_response, "status", None)
            feed_headers = _safe_response_headers(feed_response)
            feed_rendered = page.content()

            entries = []
            author = None
            login_required = False
            seen_reply_urls: set[str] = set()
            previous_page_html = None
            feed_has_entries = False
            feed_http_ok = feed_status is not None and 200 <= feed_status < 400
            if feed_http_ok:
                for _page_number in range(1, 301):
                    feed_html = page.content()
                    feed_rendered = feed_html
                    if feed_html == previous_page_html:
                        break
                    previous_page_html = feed_html
                    feed = parse_latest_reply_feed(feed_html, page.url)
                    author = author or feed.author
                    login_required = login_required or feed.login_required
                    page_entries = feed.entries
                    feed_has_entries = feed_has_entries or bool(page_entries)
                    for entry in feed.entries_for_date(target_date):
                        if entry.reply_url not in seen_reply_urls:
                            entries.append(entry)
                            seen_reply_urls.add(entry.reply_url)
                    page_dates = [
                        datetime.strptime(entry.published_at[:10], "%Y-%m-%d").date()
                        for entry in page_entries
                    ]
                    if login_required or not page_dates or min(page_dates) < requested_date:
                        break
                    next_links = page.locator("a[href^='javascript:gotoPage']")
                    if next_links.count() == 0:
                        break
                    next_links.first.click()
                    if self.settle_ms:
                        page.wait_for_timeout(self.settle_ms)

            details_by_url: dict[str, DailyReplyDetail] = {}
            page_cache: dict[str, tuple[str, str]] = {}
            article_pages_loaded = 0

            def capture_article_page(article_page) -> tuple[str, str]:
                nonlocal article_pages_loaded
                html = article_page.content()
                fingerprint = _sha256(html.encode("utf-8"))
                if fingerprint in page_cache:
                    return page_cache[fingerprint]
                snapshot = (html, article_page.url)
                page_cache[fingerprint] = snapshot
                article_pages_loaded += 1
                return snapshot

            def capture_pending(article_page, pending) -> list:
                html, page_url = capture_article_page(article_page)
                remaining = []
                for entry in pending:
                    detail = parse_associated_reply(html, page_url, entry)
                    if detail.target_found:
                        details_by_url[entry.reply_url] = detail
                    else:
                        remaining.append(entry)
                return remaining

            if feed_http_ok and not login_required:
                entries_by_article: dict[str, list] = {}
                for entry in entries:
                    entries_by_article.setdefault(entry.article_url, []).append(entry)
                for article_url, article_entries in entries_by_article.items():
                    pending = article_entries
                    page.goto(article_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    if self.settle_ms:
                        page.wait_for_timeout(self.settle_ms)
                    pending = capture_pending(page, pending)
                    for selector in ("a.prev-page", "a.next-page"):
                        if not pending:
                            break
                        if selector == "a.next-page":
                            page.goto(article_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                            if self.settle_ms:
                                page.wait_for_timeout(self.settle_ms)
                            pending = capture_pending(page, pending)
                        for _ in range(1, 101):
                            links = page.locator(selector)
                            if not pending or links.count() == 0:
                                break
                            links.first.click()
                            if self.settle_ms:
                                page.wait_for_timeout(self.settle_ms)
                            before = len(page_cache)
                            pending = capture_pending(page, pending)
                            if len(page_cache) == before:
                                break

                # A quote can omit its image from the target reply DOM.  Reuse the
                # bounded article-page cache to recover it from the original comment.
                for reply_url, detail in list(details_by_url.items()):
                    if detail.context is None or not detail.context.image_placeholder:
                        continue
                    resolved = detail.context
                    for html, page_url in page_cache.values():
                        resolved = resolve_quote_image_placeholder(html, page_url, resolved)
                        if not resolved.image_placeholder:
                            break
                    details_by_url[reply_url] = replace(detail, context=resolved)

            details = [details_by_url[entry.reply_url] for entry in entries if entry.reply_url in details_by_url]
            missing_targets = len(entries) - len(details)
            fetched_at = datetime.now().astimezone()
            archive_dir = allocate_archive_dir(
                self.output_dir, "latest-replies", f"{author or '未知作者'}-{target_date}",
                fetched_at.strftime("%Y-%m-%d-%H%M%S"),
            )
            archive_dir.mkdir(parents=True, exist_ok=False)
            assets_dir = archive_dir / "images"
            assets_dir.mkdir()
            (archive_dir / "response.html").write_bytes(feed_raw)
            rendered_bytes = feed_rendered.encode("utf-8")
            (archive_dir / "rendered.html").write_bytes(rendered_bytes)

            local_images: dict[str, str] = {}
            all_image_urls = [
                image_url for detail in details for image_url in (
                    detail.image_urls + (detail.context.image_urls if detail.context else [])
                ) if is_content_image_url(image_url)
            ]
            asset_manifest = []
            for index, image_url in enumerate(dict.fromkeys(all_image_urls), 1):
                record = {"source_url": image_url, "kind": "content", "local_file": None, "error": None}
                try:
                    image_response = context.request.get(image_url, timeout=self.timeout_ms)
                    if not image_response.ok:
                        raise RuntimeError(f"HTTP {image_response.status}")
                    content_type = image_response.headers.get("content-type")
                    image_bytes = image_response.body()
                    filename = _asset_name(image_url, content_type, index)
                    (assets_dir / filename).write_bytes(image_bytes)
                    local_file = f"images/{filename}"
                    local_images[image_url] = local_file
                    record.update(local_file=local_file, content_type=content_type, size=len(image_bytes), sha256=_sha256(image_bytes))
                except Exception as exc:
                    record["error"] = str(exc)
                asset_manifest.append(record)

            output_html = render_daily_replies_html(author, target_date, details, local_images)
            (archive_dir / "daily-replies.html").write_text(output_html, encoding="utf-8")
            reasons = []
            if not feed_http_ok:
                reasons.append(f"最新跟帖页面 HTTP {feed_status if feed_status is not None else '未知状态'}")
            if login_required:
                reasons.append("页面提示登录后查看全文")
            if feed_http_ok and not login_required and not feed_has_entries:
                reasons.append("无法解析最新跟帖页面；已保留响应与渲染诊断文件")
            if missing_targets:
                reasons.append(f"有 {missing_targets} 条目标跟帖未在主帖分页中定位到")
            incomplete_reason = "；".join(reasons) or None
            complete = incomplete_reason is None
            metadata = {
                "schema_version": 1, "source": "淘股吧", "source_url": normalized_feed_url,
                "target_date": target_date, "fetched_at": fetched_at.isoformat(),
                "status": "complete" if complete else "incomplete", "incomplete_reason": incomplete_reason,
                "author": author, "reply_count": len(details), "http_status": feed_status,
                "response_headers": feed_headers, "response_sha256": _sha256(feed_raw),
                "rendered_sha256": _sha256(rendered_bytes),
                "cache": {"article_pages_loaded": article_pages_loaded, "unique_page_snapshots": len(page_cache)},
                "replies": [
                    {"published_at": detail.entry.published_at, "text": detail.text,
                     "article_title": detail.entry.article_title, "article_url": detail.entry.article_url,
                     "reply_url": detail.entry.reply_url, "has_context": detail.context is not None,
                     "context_image_status": (
                         "not_applicable" if detail.context is None else
                         "unresolved" if detail.context.image_placeholder else
                         "present" if detail.context.image_urls else "none"
                     )}
                    for detail in details
                ], "assets": asset_manifest,
            }
            (archive_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            return DailyReplyFetchResult(normalized_feed_url, target_date, archive_dir, complete, len(details), incomplete_reason, login_required)
        finally:
            context.close()
            manager.stop()

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
