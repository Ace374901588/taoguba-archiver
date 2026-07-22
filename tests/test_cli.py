import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from taoguba_archiver.browser import BrowserFetchResult, ShuoFetchResult
from taoguba_archiver.cli import main
from taoguba_archiver.service import ArchiveBatchResult


class FakeService:
    instances = []
    shuo_complete = True

    def __init__(self):
        self.options = None
        type(self).instances.append(self)

    def archive(self, urls, options):
        self.urls = urls
        self.options = options
        item = BrowserFetchResult(urls[0], options.output_dir / "archive", True)
        return ArchiveBatchResult(items=[item])

    def login(self, options):
        self.options = options

    def collect_latest_replies(self, feed_url, target_date, options):
        self.feed_url = feed_url
        self.target_date = target_date
        self.options = options
        return type(
            "DailyResult",
            (),
            {
                "archive_dir": options.output_dir / "daily-replies",
                "reply_count": 3,
                "complete": True,
                "incomplete_reason": None,
            },
        )()

    def archive_shuo(self, shuo_url, options):
        self.shuo_url = shuo_url
        self.options = options
        return ShuoFetchResult(
            shuo_url,
            options.output_dir / "shuo",
            type(self).shuo_complete,
            None if type(self).shuo_complete else "fixture incomplete",
        )


class CliTests(unittest.TestCase):
    def setUp(self):
        FakeService.instances.clear()
        FakeService.shuo_complete = True

    def test_additive_markdown_options_reach_service(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("taoguba_archiver.cli.ArchiveService", FakeService),
        ):
            exit_code = main(
                [
                    "--output-dir",
                    temp_dir,
                    "--markdown",
                    "--markdown-images",
                    "relative",
                    "https://www.tgb.cn/a/example",
                ]
            )
        self.assertEqual(exit_code, 0)
        options = FakeService.instances[0].options
        self.assertTrue(options.export_html)
        self.assertTrue(options.export_markdown)
        self.assertEqual(options.markdown_image_mode, "relative")

    def test_markdown_only_disables_article_body_html(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("taoguba_archiver.cli.ArchiveService", FakeService),
        ):
            exit_code = main(
                [
                    "--output-dir",
                    temp_dir,
                    "--markdown",
                    "--markdown-images",
                    "source",
                    "--no-html",
                    "https://www.tgb.cn/a/example",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertFalse(FakeService.instances[0].options.export_html)

    def test_rejects_invalid_format_combinations_before_service_creation(self):
        invalid_arguments = (
            ["--markdown", "https://www.tgb.cn/a/example"],
            ["--markdown-images", "relative", "https://www.tgb.cn/a/example"],
            ["--no-html", "https://www.tgb.cn/a/example"],
        )
        with patch("taoguba_archiver.cli.ArchiveService", FakeService):
            for arguments in invalid_arguments:
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                    main(arguments)
        self.assertEqual(FakeService.instances, [])

    def test_login_ignores_archive_format_requirements(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("taoguba_archiver.cli.ArchiveService", FakeService),
        ):
            exit_code = main(
                [
                    "--login",
                    "--profile-dir",
                    str(Path(temp_dir) / "profile"),
                    "--no-html",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(FakeService.instances[0].options)

    def test_collects_an_explicit_latest_reply_feed_for_one_date(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("taoguba_archiver.cli.ArchiveService", FakeService),
        ):
            exit_code = main(
                [
                    "--output-dir",
                    temp_dir,
                    "--reply-feed",
                    "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396",
                    "--reply-date",
                    "2026-07-21",
                ]
            )
        self.assertEqual(exit_code, 0)
        service = FakeService.instances[0]
        self.assertEqual(service.target_date, "2026-07-21")
        self.assertIn("moreReplyMod", service.feed_url)

    def test_rejects_headless_latest_reply_collection(self):
        with patch("taoguba_archiver.cli.ArchiveService", FakeService):
            with self.assertRaises(SystemExit):
                main(
                    [
                        "--headless",
                        "--reply-feed",
                        "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396",
                        "--reply-date",
                        "2026-07-21",
                    ]
                )
        self.assertEqual(FakeService.instances, [])

    def test_archives_one_explicit_shuo(self):
        shuo_url = "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("taoguba_archiver.cli.ArchiveService", FakeService),
        ):
            exit_code = main(["--output-dir", temp_dir, "--shuo", shuo_url])
        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeService.instances[0].shuo_url, shuo_url)

    def test_rejects_shuo_mixed_with_incompatible_modes(self):
        shuo_url = "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"
        invalid_arguments = (
            ["--headless", "--shuo", shuo_url],
            ["https://www.tgb.cn/a/example", "--shuo", shuo_url],
            ["--urls-file", "urls.txt", "--shuo", shuo_url],
            [
                "--reply-feed",
                "https://www.tgb.cn/user/blog/moreReplyMod?userID=1",
                "--reply-date",
                "2026-07-21",
                "--shuo",
                shuo_url,
            ],
            ["--shuo", shuo_url, "--reply-date", "2026-07-21"],
            ["--markdown", "--markdown-images", "relative", "--shuo", shuo_url],
            ["--markdown", "--markdown-images", "relative", "--no-html", "--shuo", shuo_url],
        )
        with patch("taoguba_archiver.cli.ArchiveService", FakeService):
            for arguments in invalid_arguments:
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                    main(arguments)
        self.assertEqual(FakeService.instances, [])

    def test_returns_three_for_incomplete_shuo_export(self):
        FakeService.shuo_complete = False
        with patch("taoguba_archiver.cli.ArchiveService", FakeService):
            exit_code = main(
                ["--shuo", "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"]
            )
        self.assertEqual(exit_code, 3)


if __name__ == "__main__":
    unittest.main()
