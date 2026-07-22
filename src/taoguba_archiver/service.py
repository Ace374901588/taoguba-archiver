from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from .browser import BrowserFetchResult, DailyReplyFetchResult, TaogubaBrowser
from .core import validate_article_url


@dataclass(frozen=True)
class ArchiveOptions:
    profile_dir: Path
    output_dir: Path
    headless: bool = False
    include_author_replies: bool = False
    export_html: bool = True
    export_markdown: bool = False
    markdown_image_mode: str | None = None
    timeout_ms: int = 45_000
    settle_ms: int = 1_500


@dataclass(frozen=True)
class ArchiveProgress:
    completed: int
    total: int
    url: str
    archive_dir: Path
    complete: bool


@dataclass(frozen=True)
class ArchiveBatchResult:
    items: list[BrowserFetchResult]
    cancelled: bool = False

    @property
    def archives(self) -> list[Path]:
        return [item.archive_dir for item in self.items]

    @property
    def had_incomplete(self) -> bool:
        return any(not item.complete for item in self.items)


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


ProgressCallback = Callable[[ArchiveProgress], None]


class ArchiveService:
    """CLI/Web-neutral entry point for login and explicit-URL archival."""

    def __init__(self, browser_factory=TaogubaBrowser) -> None:
        self._browser_factory = browser_factory

    @staticmethod
    def _normalized_urls(urls: list[str]) -> list[str]:
        normalized = [validate_article_url(url) for url in urls]
        normalized = list(dict.fromkeys(normalized))
        if not normalized:
            raise ValueError("请至少提供一个淘股吧文章 URL")
        return normalized

    def _browser(self, options: ArchiveOptions, *, validate_exports: bool = True):
        if validate_exports:
            if not options.export_html and not options.export_markdown:
                raise ValueError("HTML 和 Markdown 至少选择一种输出格式")
            if options.export_markdown and options.markdown_image_mode not in {
                "relative",
                "source",
                "embed",
            }:
                raise ValueError("启用 Markdown 时必须选择图片模式：relative、source 或 embed")
        return self._browser_factory(
            options.profile_dir,
            options.output_dir,
            headless=options.headless,
            include_author_replies=options.include_author_replies,
            export_html=options.export_html,
            export_markdown=options.export_markdown,
            markdown_image_mode=options.markdown_image_mode,
            timeout_ms=options.timeout_ms,
            settle_ms=options.settle_ms,
        )

    def login(self, options: ArchiveOptions, *, wait_for_confirmation=None) -> None:
        self._browser(options, validate_exports=False).login(
            wait_for_confirmation=wait_for_confirmation
        )

    def archive(
        self,
        urls: list[str],
        options: ArchiveOptions,
        *,
        on_progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
    ) -> ArchiveBatchResult:
        normalized = self._normalized_urls(urls)
        browser = self._browser(options)

        def item_complete(item: BrowserFetchResult, completed: int, total: int) -> None:
            if on_progress is not None:
                on_progress(
                    ArchiveProgress(
                        completed=completed,
                        total=total,
                        url=item.url,
                        archive_dir=item.archive_dir,
                        complete=item.complete,
                    )
                )

        batch = browser.fetch_many(
            normalized,
            on_item_complete=item_complete,
            should_cancel=cancellation.is_cancelled if cancellation is not None else None,
        )
        return ArchiveBatchResult(items=batch.items, cancelled=batch.cancelled)

    def collect_latest_replies(
        self, feed_url: str, target_date: str, options: ArchiveOptions
    ) -> DailyReplyFetchResult:
        """Create one portable daily-replies export from an explicit feed URL."""
        return self._browser(options, validate_exports=False).fetch_latest_replies(
            feed_url, target_date
        )
