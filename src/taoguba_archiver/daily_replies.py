from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .core import ALLOWED_HOSTS, LOGIN_MARKERS


_DATE_TIME = re.compile(r"\b(20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\b")
_REPLY_PATH = re.compile(r"^/a/([^/?#]+)/([^/?#]+)(?:#([^/?#]+))?$")
_ARTICLE_PATH = re.compile(r"^/a/[^/?#]+$")
_TRAILING_COUNT = re.compile(r"\s*\(\d+\)\s*$")
_PICTURE_PLACEHOLDER = re.compile(r"[\[［]图片[\]］]")


@dataclass(frozen=True)
class LatestReplyEntry:
    published_at: str
    text: str
    article_title: str
    article_url: str
    reply_url: str

    @property
    def comment_id(self) -> str:
        return urlparse(self.reply_url).path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class LatestReplyFeed:
    author: str | None
    entries: list[LatestReplyEntry]
    login_required: bool

    def entries_for_date(self, date: str) -> list[LatestReplyEntry]:
        return [entry for entry in self.entries if entry.published_at.startswith(f"{date} ")]


@dataclass(frozen=True)
class ReplyContext:
    author: str | None
    published_at: str | None
    text: str
    html: str
    image_urls: list[str]
    image_placeholder: bool = False


@dataclass(frozen=True)
class DailyReplyDetail:
    entry: LatestReplyEntry
    text: str
    html: str
    context: ReplyContext | None
    image_urls: list[str]
    target_found: bool = True


def validate_reply_feed_url(url: str) -> str:
    """Accept only an explicitly supplied Taoguba latest-replies page."""
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https":
        raise ValueError(f"只允许 HTTPS URL：{candidate}")
    if (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError(f"只允许 tgb.cn 或 www.tgb.cn：{candidate}")
    if parsed.path.rstrip("/") != "/user/blog/moreReplyMod":
        raise ValueError("URL 必须是用户个人页中的“最新跟帖”链接")
    user_ids = parse_qs(parsed.query).get("userID", [])
    if len(user_ids) != 1 or not user_ids[0].isdigit():
        raise ValueError("最新跟帖 URL 必须包含数字 userID")
    return candidate


def _clean_text(element) -> str:
    if element is None:
        return ""
    lines = [line.strip() for line in element.get_text("\n", strip=True).splitlines()]
    return "\n".join(line for line in lines if line)


def _reply_links(root):
    return [
        link
        for link in root.select("a[href]")
        if _REPLY_PATH.match(urlparse(str(link.get("href"))).path)
    ]


def _entry_container(link):
    """Find the smallest feed row containing exactly one concrete reply link."""
    current = link.parent
    while current is not None and getattr(current, "name", None) not in {"body", "html"}:
        text = _clean_text(current)
        if _DATE_TIME.search(text) and len(_reply_links(current)) == 1:
            return current
        current = current.parent
    return link.parent


def parse_latest_reply_feed(html: str, page_url: str) -> LatestReplyFeed:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    heading = _clean_text(soup.select_one("h1"))
    author_match = re.match(r"(.+?)的博客$", heading)
    author = author_match.group(1).strip() if author_match else None
    entries: list[LatestReplyEntry] = []
    seen_urls: set[str] = set()

    for link in _reply_links(soup):
        reply_url = urljoin(page_url, str(link.get("href")))
        if reply_url in seen_urls:
            continue
        row = _entry_container(link)
        row_text = _clean_text(row)
        timestamp = _DATE_TIME.search(row_text)
        article_link = next(
            (
                candidate
                for candidate in row.select("a[href]")
                if _ARTICLE_PATH.match(urlparse(str(candidate.get("href"))).path)
            ),
            None,
        )
        if timestamp is None or article_link is None:
            continue
        text = _TRAILING_COUNT.sub("", _clean_text(link)).strip()
        if not text:
            continue
        entries.append(
            LatestReplyEntry(
                published_at=timestamp.group(1),
                text=text,
                article_title=_clean_text(article_link) or "无标题主帖",
                article_url=urljoin(page_url, str(article_link.get("href"))),
                reply_url=reply_url,
            )
        )
        seen_urls.add(reply_url)

    return LatestReplyFeed(
        author=author,
        entries=entries,
        login_required=any(marker in page_text for marker in LOGIN_MARKERS),
    )


def _comment_matches(block, entry: LatestReplyEntry) -> bool:
    comment_id = entry.comment_id
    for element in [block, *block.find_all(True)]:
        if f"span_{comment_id}" in element.get("class", []):
            return True
        for attribute in ("id", "data-comment-id", "data-id", "comment-id", "commentid"):
            if str(element.get(attribute, "")) == comment_id:
                return True
    text_node = block.select_one(".comment-data-text")
    text = _clean_text(text_node)
    return bool(text and entry.text in text and entry.published_at in _clean_text(block))


def _image_source(image) -> str | None:
    for attribute in ("data-original", "data-src", "src2", "src"):
        source = image.get(attribute)
        if source and not str(source).startswith("data:") and "placeholder" not in str(source).lower():
            return str(source)
    return None


def is_content_image_url(url: str) -> bool:
    """Exclude Taoguba UI emoticons; retain images embedded in comments."""
    parsed = urlparse(url)
    return not (
        (parsed.hostname or "").lower() == "css.tgb.cn"
        and "/images/face/" in parsed.path.lower()
    )


def _images_from_html(fragment: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(fragment, "html.parser")
    image_urls = []
    for image in soup.select("img"):
        source = _image_source(image)
        if not source:
            continue
        absolute = urljoin(page_url, str(source))
        if absolute not in image_urls:
            image_urls.append(absolute)
    return image_urls


def _context_from_block(block) -> ReplyContext | None:
    context = block.select_one(
        ".comment-data-reply, .comment-data-quote, .comment-reply, .reply-content, .reply-data, .quote, blockquote"
    )
    if context is None:
        return None
    author_link = context.select_one('a[href^="/blog/"]')
    timestamp = _DATE_TIME.search(_clean_text(context))
    content = context.select_one(".comment-data-text, .reply-text, p")
    text = _clean_text(content) or _clean_text(context)
    if not text:
        return None
    html = str(context)
    return ReplyContext(
        author=_clean_text(author_link) or None,
        published_at=timestamp.group(1) if timestamp else None,
        text=text,
        html=html,
        image_urls=_images_from_html(html, "https://www.tgb.cn/"),
        image_placeholder=bool(_PICTURE_PLACEHOLDER.search(text)),
    )


def _normalise_context_text(text: str) -> str:
    return re.sub(r"\s+", "", _PICTURE_PLACEHOLDER.sub("", text))


def resolve_quote_image_placeholder(
    article_html: str, page_url: str, context: ReplyContext
) -> ReplyContext:
    """Recover a quoted comment's image from its original comment page.

    Taoguba sometimes serializes a quote as literal ``［图片］`` without the image
    element.  The original comment is matched using the visible author, timestamp,
    and quote text, all within the explicitly supplied article.
    """
    if not context.image_placeholder:
        return context
    expected = _normalise_context_text(context.text)
    if not expected:
        return context
    soup = BeautifulSoup(article_html, "html.parser")
    for block in soup.select(".comment-data"):
        author = _clean_text(block.select_one('.comment-data-user a, a[href^="/blog/"]')) or None
        timestamp = _DATE_TIME.search(_clean_text(block))
        content = block.select_one(".comment-data-text")
        text = _clean_text(content)
        if (
            (author is not None and context.author is not None and author != context.author)
            or (timestamp.group(1) if timestamp else None) != context.published_at
            or _normalise_context_text(text) != expected
        ):
            continue
        content_html = str(content) if content is not None else context.html
        image_urls = _images_from_html(content_html, page_url)
        if image_urls:
            return ReplyContext(
                author or context.author,
                context.published_at,
                text,
                content_html,
                image_urls,
                False,
            )
    return context


def parse_associated_reply(
    html: str, page_url: str, entry: LatestReplyEntry
) -> DailyReplyDetail:
    """Extract a target reply and only the context embedded with that reply."""
    soup = BeautifulSoup(html, "html.parser")
    target = next((block for block in soup.select(".comment-data") if _comment_matches(block, entry)), None)
    if target is None:
        return DailyReplyDetail(entry, entry.text, f"<p>{escape(entry.text)}</p>", None, [], False)

    content = target.select_one(".comment-data-text")
    content_html = str(content) if content is not None else f"<p>{escape(entry.text)}</p>"
    return DailyReplyDetail(
        entry=entry,
        text=_clean_text(content) or entry.text,
        html=content_html,
        context=_context_from_block(target),
        image_urls=_images_from_html(content_html, page_url),
    )


def _portable_fragment(
    html: str,
    page_url: str,
    local_images: dict[str, str],
    *,
    strip_context_metadata: bool = False,
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, iframe, object, embed"):
        tag.decompose()
    for tag in soup.find_all(True):
        for attribute in list(tag.attrs):
            if attribute.lower().startswith("on"):
                tag.attrs.pop(attribute, None)
    if strip_context_metadata:
        for tag in soup.select('a[href^="/blog/"], time'):
            tag.decompose()
        for tag in soup.find_all("span"):
            if _DATE_TIME.fullmatch(_clean_text(tag)):
                tag.decompose()
    for image in soup.select("img"):
        source = _image_source(image)
        local_path = local_images.get(urljoin(page_url, str(source))) if source else None
        if local_path:
            image["src"] = local_path
            image["loading"] = "lazy"
            image["decoding"] = "async"
        else:
            image.decompose()
            continue
        for attribute in ("data-original", "data-src", "src2"):
            image.attrs.pop(attribute, None)
    return str(soup)


def render_daily_replies_html(
    author: str | None,
    date: str,
    details: list[DailyReplyDetail],
    local_images: dict[str, str],
) -> str:
    safe_author = escape(author or "未知作者")
    cards = []
    for detail in details:
        entry = detail.entry
        time_label = entry.published_at.split(" ", 1)[-1]
        body = _portable_fragment(detail.html, entry.reply_url, local_images)
        context = ""
        if detail.context is not None:
            context_body = _portable_fragment(
                detail.context.html,
                entry.reply_url,
                local_images,
                strip_context_metadata=True,
            )
            context_meta = " · ".join(
                value
                for value in (detail.context.author, detail.context.published_at)
                if value
            )
            context = (
                f"<aside class=\"context\"><p class=\"label\">关联回复</p>"
                f"<div class=\"context-meta\">{escape(context_meta)}</div>{context_body}</aside>"
            )
        cards.append(
            f"<article class=\"timeline-item\"><div class=\"timeline-rail\">"
            f"<time>{escape(time_label)}</time><span class=\"timeline-node\"></span></div>"
            f"<div class=\"timeline-content\"><header class=\"reply-meta\">"
            f"<a href=\"{escape(entry.article_url, quote=True)}\" target=\"_blank\" rel=\"noreferrer\">{escape(entry.article_title)}</a>"
            f"<a class=\"source\" href=\"{escape(entry.reply_url, quote=True)}\" target=\"_blank\" rel=\"noreferrer\">原帖定位</a>"
            f"</header><section class=\"reply-body\">{body}</section>{context}</div></article>"
        )
    empty = "<p class=\"empty\">该日期没有符合条件的跟帖。</p>" if not cards else ""
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{safe_author} · {escape(date)} 跟帖整理</title><style>
:root{{--page:#f5f7fb;--surface:#fff;--ink:#172033;--muted:#64748b;--line:#dce3ed;--brand:#0f766e;--quote:#eefbf8}}*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);font:15px/1.72 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}main{{width:min(100% - 48px,1440px);margin:24px auto 48px}}header.page{{padding:24px 30px;background:var(--surface);border:1px solid var(--line);border-top:4px solid var(--brand);border-radius:14px}}h1{{margin:0;font-size:clamp(24px,3vw,34px);letter-spacing:-.02em}}.summary{{margin:8px 0 0;color:var(--muted)}}a{{color:var(--brand);text-decoration:none}}a:hover{{text-decoration:underline}}.timeline-item{{display:grid;grid-template-columns:88px minmax(0,1fr);gap:0}}.timeline-rail{{position:relative;padding:20px 20px 0 0;text-align:right;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}}.timeline-rail:after{{content:"";position:absolute;right:0;top:38px;bottom:-1px;width:1px;background:var(--line)}}.timeline-node{{position:absolute;right:-5px;top:24px;width:10px;height:10px;border:2px solid var(--page);border-radius:50%;background:var(--brand)}}.timeline-content{{min-width:0;padding:18px 0 22px 30px;border-bottom:1px solid var(--line)}}.reply-meta{{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;color:var(--muted);font-size:13px}}.reply-meta>a:first-child{{font-weight:680}}.source{{margin-left:auto;font-size:12px}}.reply-body{{margin-top:10px;overflow-wrap:anywhere}}.reply-body p,.context p{{margin:0 0 .75em}}.reply-body>:last-child,.context>:last-child{{margin-bottom:0}}img{{display:block;max-width:100%;height:auto;margin:12px 0;border-radius:8px}}.context{{margin-top:14px;padding:10px 14px;border-left:3px solid #2dd4bf;background:var(--quote);font-size:14px}}.label{{margin:0;color:var(--brand);font-size:12px;font-weight:750}}.context-meta{{margin:1px 0 7px;color:var(--muted);font-size:12px}}.empty{{margin:18px 0;padding:22px 30px;background:#fff;border:1px solid var(--line);border-radius:12px;color:var(--muted)}}@media(max-width:720px){{main{{width:min(100% - 24px,1440px);margin:12px auto 28px}}header.page{{padding:20px}}.timeline-item{{grid-template-columns:60px minmax(0,1fr)}}.timeline-rail{{padding-right:15px}}.timeline-content{{padding-left:20px}}.source{{margin-left:0}}}}
</style></head><body><main><header class=\"page\"><h1>{safe_author} · {escape(date)} 跟帖整理</h1><p class=\"summary\">共 {len(details)} 条；仅保留目标跟帖及其页面内直接关联的回复。</p></header>{empty}{''.join(cards)}</main></body></html>"""
