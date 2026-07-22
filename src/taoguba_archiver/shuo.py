from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .core import LOGIN_MARKERS


_SHUO_HOST = "shuo.tgb.cn"
_SHUO_PATH = "/shuo/toViewShuo"
_TITLE_SELECTORS = (".shuo-title",)
_AUTHOR_SELECTORS = (".shuo-author",)
_TIME_SELECTORS = (".shuo-time",)
_BODY_SELECTORS = (".shuo-content",)
_IMAGE_ATTRIBUTES = ("data-original", "data-src", "src2", "src")


@dataclass(frozen=True)
class ShuoContent:
    title: str
    author: str | None
    published_at: str | None
    body_text: str
    body_html: str
    image_urls: list[str]
    login_required: bool


def validate_shuo_url(url: str) -> str:
    """Accept only an explicitly supplied single Taoguba shuo URL."""
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https":
        raise ValueError(f"只允许 HTTPS URL：{candidate}")
    if (parsed.hostname or "").lower() != _SHUO_HOST:
        raise ValueError(f"只允许 shuo.tgb.cn：{candidate}")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("说说 URL 不能包含用户信息或片段")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("说说 URL 端口无效") from exc
    if port not in (None, 443):
        raise ValueError("说说 URL 不能使用非默认端口")
    if parsed.path.rstrip("/") != _SHUO_PATH:
        raise ValueError("URL 必须是单条说说页面")
    try:
        query_items = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("说说 URL 查询参数无效") from exc
    if len(query_items) != 1 or query_items[0][0] != "shuoID" or not query_items[0][1].isdigit():
        raise ValueError("说说 URL 必须包含数字 shuoID")
    return urlunparse(("https", _SHUO_HOST, _SHUO_PATH, "", urlencode(query_items), ""))


def _clean_text(element) -> str:
    if element is None:
        return ""
    lines = [line.strip() for line in element.get_text("\n", strip=True).splitlines()]
    return "\n".join(line for line in lines if line)


def _first(soup: BeautifulSoup, selectors: tuple[str, ...]):
    for selector in selectors:
        element = soup.select_one(selector)
        if element is not None:
            return element
    return None


def _image_source(image, page_url: str) -> str | None:
    for attribute in _IMAGE_ATTRIBUTES:
        source = image.get(attribute)
        if not source:
            continue
        absolute = urljoin(page_url, str(source))
        parsed = urlparse(absolute)
        if (
            parsed.scheme not in {"http", "https"}
            or (parsed.hostname or "").lower() == "css.tgb.cn"
            or "placeholder" in absolute.lower()
        ):
            continue
        return absolute
    return None


def _sanitize_body(body, page_url: str) -> tuple[str, list[str]]:
    fragment = BeautifulSoup(str(body), "html.parser")
    for tag in fragment.select("script, style, iframe, object, embed"):
        tag.decompose()
    for tag in fragment.find_all(True):
        for attribute in list(tag.attrs):
            if attribute.lower().startswith("on"):
                tag.attrs.pop(attribute, None)

    image_urls: list[str] = []
    for image in fragment.select("img"):
        source = _image_source(image, page_url)
        if source is None:
            image.decompose()
            continue
        image["src"] = source
        for attribute in ("data-original", "data-src", "src2"):
            image.attrs.pop(attribute, None)
        if source not in image_urls:
            image_urls.append(source)
    return str(fragment), image_urls


def parse_shuo(html: str, page_url: str) -> ShuoContent:
    """Parse only the title, metadata, and body of one supplied shuo page."""
    soup = BeautifulSoup(html, "html.parser")
    title = _clean_text(_first(soup, _TITLE_SELECTORS)) or "无标题"
    author = _clean_text(_first(soup, _AUTHOR_SELECTORS)) or None
    published_at = _clean_text(_first(soup, _TIME_SELECTORS)) or None
    body = _first(soup, _BODY_SELECTORS)
    body_html, image_urls = _sanitize_body(body, page_url) if body is not None else ("", [])
    page_text = soup.get_text(" ", strip=True)
    return ShuoContent(
        title=title,
        author=author,
        published_at=published_at,
        body_text=_clean_text(BeautifulSoup(body_html, "html.parser")),
        body_html=body_html,
        image_urls=image_urls,
        login_required=any(marker in page_text for marker in LOGIN_MARKERS),
    )


def _portable_body(html: str, local_images: dict[str, str]) -> str:
    fragment = BeautifulSoup(html, "html.parser")
    for tag in fragment.select("script, style, iframe, object, embed"):
        tag.decompose()
    for tag in fragment.find_all(True):
        for attribute in list(tag.attrs):
            if attribute.lower().startswith("on"):
                tag.attrs.pop(attribute, None)
    for image in fragment.select("img"):
        source = str(image.get("src", ""))
        local_path = local_images.get(source)
        if local_path is None:
            image.decompose()
            continue
        image["src"] = local_path
        image["loading"] = "lazy"
        image["decoding"] = "async"
        for attribute in ("data-original", "data-src", "src2"):
            image.attrs.pop(attribute, None)
    return str(fragment)


def render_shuo_html(
    content: ShuoContent, local_images: dict[str, str], source_url: str
) -> str:
    """Render a portable HTML page containing only the parsed shuo content."""
    author = escape(content.author or "未知作者")
    published_at = escape(content.published_at or "发布时间未知")
    body = _portable_body(content.body_html, local_images)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(content.title)}</title><style>
:root{{--page:#f5f7fb;--surface:#fff;--ink:#172033;--muted:#64748b;--line:#dce3ed;--brand:#0f766e}}*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);font:16px/1.75 system-ui,sans-serif}}main{{width:min(100% - 32px,900px);margin:24px auto 48px;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:28px}}h1{{margin:0;font-size:clamp(24px,4vw,34px)}}.meta{{margin:10px 0 24px;color:var(--muted);font-size:14px}}.meta a{{color:var(--brand);text-decoration:none}}.body{{overflow-wrap:anywhere}}.body img{{display:block;max-width:100%;height:auto;margin:14px 0;border-radius:8px}}.source{{margin-top:28px;padding-top:16px;border-top:1px solid var(--line);font-size:13px}}.source a{{color:var(--brand)}}
</style></head><body><main><article><h1>{escape(content.title)}</h1><p class="meta">{author} · {published_at}</p><section class="body">{body}</section></article><p class="source"><a href="{escape(source_url, quote=True)}" target="_blank" rel="noreferrer">查看原说说</a></p></main></body></html>'''
