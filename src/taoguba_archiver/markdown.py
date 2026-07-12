from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from .core import ParsedArticle


IMAGE_MODES = {"relative", "source", "embed"}


def _render_emphasis(content: str, marker: str) -> str:
    """Keep Markdown emphasis within a line and outside paired punctuation."""
    ends_with_line_break = bool(re.search(r"\n\s*$", content))
    lines = content.strip().splitlines()
    rendered = "\n".join(
        _render_emphasis_line(line.strip(), marker) if line.strip() else "" for line in lines
    )
    return f"{rendered}\n\n" if ends_with_line_break else rendered


def _render_emphasis_line(text: str, marker: str) -> str:
    for opening, closing in (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")):
        if text.startswith(opening) and text.endswith(closing) and len(text) > len(opening) + len(closing):
            return f"{opening}{marker}{text[len(opening):-len(closing)]}{marker}{closing}"
    link_match = re.fullmatch(r"\[([^]]+)\]\((.+)\)([：:，,。！？!?；;、]*)", text)
    if link_match:
        label, url, punctuation = link_match.groups()
        return f"[{marker}{label}{marker}]({url}){punctuation}"
    return f"{marker}{text}{marker}"


class _MarkdownRenderer:
    def __init__(
        self, page_url: str, assets: list[dict], image_mode: str, archive_dir: Path | None
    ):
        self.page_url = page_url
        self.assets = {record["source_url"]: record for record in assets}
        self.image_mode = image_mode
        self.archive_dir = archive_dir

    def image_target(self, tag: Tag) -> str:
        source = tag.get("data-original") or tag.get("data-src") or tag.get("src") or ""
        absolute = urljoin(self.page_url, str(source))
        record = self.assets.get(absolute, {})
        local_file = record.get("local_file")
        if self.image_mode == "source" or not local_file:
            return absolute
        if self.image_mode == "relative":
            return str(local_file).replace("\\", "/")
        path = self.archive_dir / local_file
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        content_type = record.get("content_type") or "application/octet-stream"
        return f"data:{content_type};base64,{data}"

    def render_children(self, tag: Tag) -> str:
        return "".join(self.render(child) for child in tag.children)

    def render(self, node) -> str:
        if isinstance(node, NavigableString):
            return re.sub(r"\s+", " ", str(node))
        if not isinstance(node, Tag):
            return ""

        name = node.name.lower()
        if name in {"script", "style", "noscript"}:
            return ""
        if name in {"strong", "b"}:
            content = self.render_children(node)
            return _render_emphasis(content, "**")
        if name in {"em", "i"}:
            return _render_emphasis(self.render_children(node), "*")
        if name == "a":
            label = self.render_children(node).strip()
            href = urljoin(self.page_url, str(node.get("href") or ""))
            return f"[{label}]({href})" if href else label
        if name == "img":
            alt = str(node.get("alt") or "图片").strip()
            return f"\n\n![{alt}]({self.image_target(node)})\n\n"
        if name == "br":
            return "  \n"
        if name == "code" and node.parent and node.parent.name != "pre":
            return f"`{node.get_text()}`"
        if name == "pre":
            return f"\n\n```\n{node.get_text().strip()}\n```\n\n"
        if name in {f"h{level}" for level in range(1, 7)}:
            level = int(name[1])
            return f"\n\n{'#' * level} {self.render_children(node).strip()}\n\n"
        if name == "blockquote":
            content = self.render_children(node).strip()
            quoted = "\n".join(f"> {line}" for line in content.splitlines())
            return f"\n\n{quoted}\n\n"
        if name in {"ul", "ol"}:
            lines = []
            for index, item in enumerate(node.find_all("li", recursive=False), 1):
                marker = "-" if name == "ul" else f"{index}."
                content = self.render_children(item).strip()
                lines.append(f"{marker} {content}")
            rendered_lines = "\n".join(lines)
            return f"\n\n{rendered_lines}\n\n"
        content = self.render_children(node)
        if name in {"p", "div", "section", "article", "figure", "figcaption"}:
            return f"\n\n{content.strip()}\n\n"
        return content


def render_article_markdown(
    article: ParsedArticle,
    page_url: str,
    assets: list[dict],
    *,
    image_mode: str,
    archive_dir: Path | None = None,
) -> str:
    if image_mode not in IMAGE_MODES:
        raise ValueError(f"未知 Markdown 图片模式：{image_mode}")
    if image_mode == "embed" and archive_dir is None:
        raise ValueError("内嵌图片模式需要 archive_dir")

    soup = BeautifulSoup(article.main_html, "html.parser")
    renderer = _MarkdownRenderer(page_url, assets, image_mode, archive_dir)
    body = "".join(renderer.render(child) for child in soup.contents)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    header = [f"# {article.title}"]
    if article.author:
        header.append(f"- 作者：{article.author}")
    if article.published_at:
        header.append(f"- 发布时间：{article.published_at}")
    header.append(f"- 原文：{page_url}")
    parts = ["\n".join(header), body]
    if article.author_replies:
        replies = "\n\n".join(
            f"{index}. {reply}" for index, reply in enumerate(article.author_replies, 1)
        )
        parts.append(f"## 楼主跟帖\n\n{replies}")
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"
