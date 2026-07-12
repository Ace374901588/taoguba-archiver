import tempfile
import unittest
from pathlib import Path

from taoguba_archiver.browser import BrowserBatchResult, BrowserFetchResult
from taoguba_archiver.service import (
    ArchiveOptions,
    ArchiveService,
    CancellationToken,
)


class FakeBrowser:
    instances = []

    def __init__(self, profile_dir, output_dir, **kwargs):
        self.profile_dir = profile_dir
        self.output_dir = output_dir
        self.kwargs = kwargs
        self.urls = []
        type(self).instances.append(self)

    def fetch_many(self, urls, *, on_item_complete=None, should_cancel=None):
        self.urls = list(urls)
        items = []
        for index, url in enumerate(urls, 1):
            if should_cancel and should_cancel():
                return BrowserBatchResult(items=items, cancelled=True)
            item = BrowserFetchResult(
                url=url,
                archive_dir=self.output_dir / f"archive-{index}",
                complete="incomplete" not in url,
                incomplete_reason="页面提示登录后查看全文" if "incomplete" in url else None,
                login_required="incomplete" in url,
            )
            items.append(item)
            if on_item_complete:
                on_item_complete(item, index, len(urls))
        return BrowserBatchResult(items=items, cancelled=False)

    def login(self, wait_for_confirmation=None):
        self.login_called = True
        if wait_for_confirmation:
            wait_for_confirmation()


class ArchiveServiceTests(unittest.TestCase):
    def setUp(self):
        FakeBrowser.instances.clear()

    def test_validates_deduplicates_and_returns_structured_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            options = ArchiveOptions(
                profile_dir=root / "profile",
                output_dir=root / "exports",
                export_html=True,
                export_markdown=True,
                markdown_image_mode="relative",
            )
            progress = []
            service = ArchiveService(browser_factory=FakeBrowser)

            result = service.archive(
                [
                    " https://www.tgb.cn/a/first ",
                    "https://www.tgb.cn/a/first",
                    "https://www.tgb.cn/a/incomplete",
                ],
                options,
                on_progress=progress.append,
            )

            self.assertFalse(result.cancelled)
            self.assertTrue(result.had_incomplete)
            self.assertEqual(len(result.items), 2)
            self.assertEqual([event.completed for event in progress], [1, 2])
            self.assertEqual(
                FakeBrowser.instances[0].urls,
                [
                    "https://www.tgb.cn/a/first",
                    "https://www.tgb.cn/a/incomplete",
                ],
            )
            self.assertTrue(FakeBrowser.instances[0].kwargs["export_html"])
            self.assertTrue(FakeBrowser.instances[0].kwargs["export_markdown"])
            self.assertEqual(FakeBrowser.instances[0].kwargs["markdown_image_mode"], "relative")

    def test_rejects_empty_input_and_disabling_all_formats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = ArchiveService(browser_factory=FakeBrowser)
            with self.assertRaises(ValueError):
                service.archive([], ArchiveOptions(root / "profile", root / "exports"))
            with self.assertRaises(ValueError):
                service.archive(
                    ["https://www.tgb.cn/a/example"],
                    ArchiveOptions(
                        root / "profile",
                        root / "exports",
                        export_html=False,
                        export_markdown=False,
                    ),
                )

    def test_cancellation_stops_before_next_article(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            token = CancellationToken()
            events = []

            def cancel_after_first(event):
                events.append(event)
                token.cancel()

            result = ArchiveService(browser_factory=FakeBrowser).archive(
                ["https://www.tgb.cn/a/one", "https://www.tgb.cn/a/two"],
                ArchiveOptions(root / "profile", root / "exports"),
                on_progress=cancel_after_first,
                cancellation=token,
            )

            self.assertTrue(result.cancelled)
            self.assertEqual(len(result.items), 1)
            self.assertEqual(len(events), 1)

    def test_login_does_not_require_export_format_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            options = ArchiveOptions(
                root / "profile",
                root / "exports",
                export_html=False,
                export_markdown=False,
            )
            confirmed = []
            ArchiveService(browser_factory=FakeBrowser).login(
                options, wait_for_confirmation=lambda: confirmed.append(True)
            )
            self.assertTrue(FakeBrowser.instances[0].login_called)
            self.assertEqual(confirmed, [True])


if __name__ == "__main__":
    unittest.main()
