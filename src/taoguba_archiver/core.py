from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


ALLOWED_HOSTS = {"tgb.cn", "www.tgb.cn"}
LOGIN_MARKERS = ("登录可查看全文", "登录后可查看全文")


@dataclass(frozen=True)
class ParsedArticle:
    title: str
    author: str | None
    published_at: str | None
    main_text: str
    main_html: str
    author_replies: list[str]
    image_urls: list[str]
    login_required: bool


def validate_article_url(url: str) -> str:
    """只接受淘股吧 HTTPS 页面，避免把登录态带到其他站点。"""
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https":
        raise ValueError(f"只允许 HTTPS URL：{candidate}")
    if (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError(f"只允许 tgb.cn 或 www.tgb.cn：{candidate}")
    if not parsed.path or parsed.path == "/":
        raise ValueError(f"URL 不是文章页面：{candidate}")
    return candidate


def article_key_from_url(url: str) -> str:
    path_parts = [part for part in urlparse(validate_article_url(url)).path.split("/") if part]
    if not path_parts:
        return "unknown"
    if path_parts[0].lower() == "article" and len(path_parts) >= 2:
        return "-".join(path_parts[1:3])
    if path_parts[0].lower() in {"a", "bbs"} and len(path_parts) >= 2:
        return path_parts[1]
    return "-".join(path_parts[-2:])


def _clean_text(element) -> str:
    if element is None:
        return ""
    text = element.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        element = soup.select_one(selector)
        if element and element.get("content"):
            return str(element["content"]).strip() or None
    return None


def parse_article(
    html: str,
    page_url: str,
    *,
    include_author_replies: bool = False,
) -> ParsedArticle:
    soup = BeautifulSoup(html, "html.parser")

    title_element = soup.select_one("#stockTitle, .article-tittle, h1")
    title = _clean_text(title_element)
    if not title:
        title = _meta_content(soup, 'meta[property="og:title"]') or "无标题"

    author = _meta_content(soup, 'meta[property="og:author"]', 'meta[name="author"]')
    published_at = _meta_content(
        soup,
        'meta[property="article:published_time"]',
        'meta[name="publishdate"]',
    )

    main = soup.select_one("#first, .article-text.p_coten")
    main_text = _clean_text(main)
    main_html = str(main) if main is not None else ""

    author_replies: list[str] = []
    if include_author_replies:
        for block in soup.select(".comment-data"):
            user_info = block.select_one(".comment-data-user")
            if user_info is None or "楼主" not in _clean_text(user_info):
                continue
            reply_text = _clean_text(block.select_one(".comment-data-text"))
            if reply_text:
                author_replies.append(reply_text)

    image_urls: list[str] = []
    image_roots = [main] if main is not None else []
    if include_author_replies:
        for block in soup.select(".comment-data"):
            user_info = block.select_one(".comment-data-user")
            if user_info is not None and "楼主" in _clean_text(user_info):
                image_roots.append(block.select_one(".comment-data-text"))
    for root in image_roots:
        if root is None:
            continue
        for image in root.select("img"):
            source = image.get("data-original") or image.get("data-src") or image.get("src")
            if not source or str(source).startswith("data:"):
                continue
            absolute = urljoin(page_url, str(source))
            if absolute not in image_urls:
                image_urls.append(absolute)

    page_text = soup.get_text(" ", strip=True)
    login_required = any(marker in page_text for marker in LOGIN_MARKERS)

    return ParsedArticle(
        title=title,
        author=author,
        published_at=published_at,
        main_text=main_text,
        main_html=main_html,
        author_replies=author_replies,
        image_urls=image_urls,
        login_required=login_required,
    )


def safe_filename(value: str, max_length: int = 80) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value)
    cleaned = re.sub(r"\s+", "-", cleaned).strip(" .-")
    return cleaned[:max_length].rstrip(" .-") or "无标题"


def allocate_archive_dir(root: Path, article_key: str, title: str, now: str) -> Path:
    base_name = safe_filename(f"{now}-{article_key}-{title}")
    candidate = root / base_name
    suffix = 2
    while candidate.exists():
        candidate = root / f"{base_name}-{suffix}"
        suffix += 1
    return candidate
