import tempfile
import threading
import tomllib
import unittest
from urllib.request import urlopen
from pathlib import Path

from taoguba_archiver.browser import BrowserFetchResult
from taoguba_archiver.service import ArchiveBatchResult
from taoguba_archiver.settings import SettingsStore
from taoguba_archiver.web import WebApp, serve


class FakeService:
    def archive(self, urls, options, *, on_progress, cancellation):
        item = BrowserFetchResult(urls[0], options.output_dir / "archive", True)
        on_progress(type("Progress", (), {"completed": 1, "total": 1, "url": urls[0], "complete": True})())
        return ArchiveBatchResult(items=[item])

    def collect_latest_replies(self, feed_url, target_date, options):
        self.feed_url = feed_url
        self.target_date = target_date
        return type(
            "DailyResult",
            (),
            {
                "archive_dir": options.output_dir / "daily-replies",
                "reply_count": 2,
                "complete": True,
                "login_required": False,
            },
        )()


class WebAppTests(unittest.TestCase):
    def test_project_exposes_only_cli_and_browser_application_entries(self):
        project_root = Path(__file__).resolve().parents[1]
        config = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("taoguba-archiver", config["project"]["scripts"])
        self.assertIn("taoguba-archiver-web", config["project"]["scripts"])
        self.assertNotIn("taoguba-archiver-gui", config["project"]["scripts"])
        self.assertNotIn("gui", config["project"].get("optional-dependencies", {}))
        self.assertNotIn("build", config["project"].get("optional-dependencies", {}))

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.selected_directory: Path | None = None
        self.picker_initial_directory: str | None = None

        def folder_picker(initial_directory: str | None) -> str | None:
            self.picker_initial_directory = initial_directory
            return str(self.selected_directory) if self.selected_directory else None

        self.app = WebApp(
            settings_store=SettingsStore(root / "settings.json"),
            service=FakeService(),
            profile_dir=root / "profile",
            folder_picker=folder_picker,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_round_trip_for_browser_ui(self):
        state = self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": True,
                "markdown_image_mode": "relative",
                "include_author_replies": True,
            }
        )

        self.assertEqual(state["settings"]["markdown_image_mode"], "relative")
        self.assertTrue(state["settings"]["include_author_replies"])

    def test_markdown_defaults_to_relative_images_when_mode_is_omitted(self):
        state = self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": True,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )

        self.assertEqual(state["settings"]["markdown_image_mode"], "relative")

    def test_select_output_dir_uses_native_picker_and_persists_the_selection(self):
        selected_directory = Path(self.temp_dir.name) / "exports"
        selected_directory.mkdir()
        self.selected_directory = selected_directory

        state = self.app.select_output_dir()

        self.assertEqual(state["settings"]["output_dir"], str(selected_directory))
        self.assertTrue(state["output_dir_selected"])
        self.assertIsNone(self.picker_initial_directory)

        self.selected_directory = None
        unchanged = self.app.select_output_dir()
        self.assertEqual(unchanged["settings"]["output_dir"], str(selected_directory))
        self.assertFalse(unchanged["output_dir_selected"])
        self.assertEqual(self.picker_initial_directory, str(selected_directory))

    def test_archive_appends_progress_events_for_browser_polling(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )

        self.app.start_archive(["https://www.tgb.cn/a/example"])
        self.app.wait_for_idle(timeout=1)

        messages = [event["message"] for event in self.app.state()["events"]]
        self.assertIn("开始归档：共 1 篇文章", messages)
        self.assertIn("完成  ·  https://www.tgb.cn/a/example", messages)
        self.assertIn("归档完成", messages)

    def test_archive_rejects_an_empty_url_list_before_starting_a_worker(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )

        with self.assertRaisesRegex(ValueError, "请至少提供一个淘股吧文章 URL"):
            self.app.start_archive([])

    def test_collects_explicit_latest_replies_in_a_background_worker(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )

        self.app.start_latest_replies(
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396", "2026-07-21"
        )
        self.app.wait_for_idle(timeout=1)

        messages = [event["message"] for event in self.app.state()["events"]]
        self.assertIn("开始整理最新跟帖：2026-07-21", messages)
        self.assertIn("最新跟帖整理完成：共 2 条", messages)

    def test_local_server_serves_browser_workspace_on_loopback(self):
        server = serve(port=0, open_browser=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=1) as response:
                page = response.read().decode("utf-8")
            self.assertIn("淘股吧文章归档器", page)
            self.assertIn("/api/archive", page)
            self.assertIn("/api/latest-replies", page)
            self.assertIn('id="replyFeed"', page)
            self.assertIn('id="replyDate" type="date"', page)
            self.assertIn('class="app-shell"', page)
            self.assertIn('aria-live="polite"', page)
            self.assertIn('id="selectOutput"', page)
            self.assertIn("/api/output-dir", page)
            self.assertIn(
                ".stack,.settings{gap:20px}.settings{grid-template-columns:1fr}",
                page,
            )
            self.assertIn(
                "$('markdownMode').value=s.markdown_image_mode||'relative'",
                page,
            )
            self.assertIn(
                '<option value="relative" selected>相对路径（便于随导出包移动）</option>',
                page,
            )
            self.assertNotIn('<option value="">选择图片方式…</option>', page)
            self.assertIn('id="markdownModeField" class="field" hidden', page)
            self.assertIn("[hidden]{display:none!important}", page)
            self.assertIn(
                "$('markdownModeField').hidden=!s.export_markdown",
                page,
            )
            self.assertIn(
                "$('markdownModeField').hidden=!$('markdown').checked;updateArchiveAvailability();save()",
                page,
            )
            self.assertIn("function archiveUnavailableReason()", page)
            self.assertIn(
                "if(!$('urls').value.trim())return '请输入至少一个文章链接'",
                page,
            )
            self.assertIn("$('archive').disabled=Boolean(reason)", page)
            self.assertIn(
                ".primary:disabled,.primary:disabled:hover{background:#cbd5e1",
                page,
            )
            self.assertIn(r"join('\n')", page)
            self.assertIn(r"split(/\r?\n/)", page)
            self.assertIn("@media(max-width:900px)", page)
            self.assertIn(
                ".log{background:#fff;color:#0f172a;border-color:#cbd5e1;padding:9px}",
                page,
            )
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
