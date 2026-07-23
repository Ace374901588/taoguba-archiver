import json
import tempfile
import threading
import tomllib
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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

    def archive_shuo(self, shuo_url, options):
        self.shuo_calls = getattr(self, "shuo_calls", 0) + 1
        self.shuo_url = shuo_url
        self.shuo_thread = threading.current_thread()
        if started := getattr(self, "shuo_started", None):
            started.set()
        if release := getattr(self, "shuo_release", None):
            release.wait(timeout=2)
        complete = getattr(self, "shuo_complete", True)
        return type(
            "ShuoResult",
            (),
            {
                "url": shuo_url,
                "archive_dir": options.output_dir / "shuo-archive",
                "complete": complete,
                "incomplete_reason": None if complete else "页面拒绝访问",
                "login_required": getattr(self, "shuo_login_required", False),
            },
        )()

    def login(self, options, *, wait_for_confirmation):
        if started := getattr(self, "login_started", None):
            started.set()
        wait_for_confirmation()


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

    def test_archives_one_explicit_shuo_url_in_a_background_worker(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )
        shuo_url = (
            "https://shuo.tgb.cn/shuo/toViewShuo?"
            "shuoID=2079570335635705862"
        )

        self.app.start_shuo(shuo_url)
        self.app.wait_for_idle(timeout=1)

        messages = [event["message"] for event in self.app.state()["events"]]
        self.assertIn("开始归档说说", messages)
        self.assertIn(
            f"说说归档完成：{Path(self.temp_dir.name) / 'exports' / 'shuo-archive'}",
            messages,
        )
        self.assertEqual(self.app.service.shuo_url, shuo_url)
        self.assertIsNot(self.app.service.shuo_thread, threading.current_thread())

    def test_shuo_rejects_a_non_shuo_url_before_starting_a_worker(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )

        with self.assertRaisesRegex(ValueError, "shuo.tgb.cn"):
            self.app.start_shuo("https://www.tgb.cn/a/example")

        self.assertIsNone(self.app._worker)

    def test_shuo_changes_login_state_only_when_login_is_required(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )
        shuo_url = (
            "https://shuo.tgb.cn/shuo/toViewShuo?"
            "shuoID=2079570335635705862"
        )
        self.app.service.shuo_complete = False

        self.app.start_shuo(shuo_url)
        self.app.wait_for_idle(timeout=1)

        state = self.app.state()
        self.assertEqual(state["login_status"], "未登录")
        self.assertIn(
            "说说归档不完整：页面拒绝访问",
            [event["message"] for event in state["events"]],
        )

        self.app.service.shuo_login_required = True
        self.app.start_shuo(shuo_url)
        self.app.wait_for_idle(timeout=1)

        self.assertEqual(self.app.state()["login_status"], "登录失效；请重新登录")

    def test_shuo_api_requires_same_origin_json_and_workspace_token(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )
        server = serve(port=0, open_browser=False)
        server.RequestHandlerClass.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/api/shuo"
        origin = f"http://127.0.0.1:{server.server_port}"
        body = json.dumps(
            {
                "shuo_url": (
                    "https://shuo.tgb.cn/shuo/toViewShuo?"
                    "shuoID=2079570335635705862"
                )
            }
        ).encode("utf-8")

        def post(headers):
            request = Request(endpoint, data=body, headers=headers, method="POST")
            return urlopen(request, timeout=1)

        try:
            invalid_headers = [
                {
                    "Content-Type": "application/json",
                    "X-Taoguba-Session-Token": self.app.session_token,
                },
                {
                    "Origin": "https://attacker.example",
                    "Content-Type": "application/json",
                    "X-Taoguba-Session-Token": self.app.session_token,
                },
                {
                    "Origin": origin,
                    "X-Taoguba-Session-Token": self.app.session_token,
                },
                {
                    "Origin": origin,
                    "Content-Type": "text/plain",
                    "X-Taoguba-Session-Token": self.app.session_token,
                },
                {
                    "Origin": origin,
                    "Content-Type": "application/json",
                },
                {
                    "Origin": origin,
                    "Content-Type": "application/json",
                    "X-Taoguba-Session-Token": "wrong-token",
                },
            ]
            for headers in invalid_headers:
                with self.subTest(headers=headers):
                    with self.assertRaises(HTTPError):
                        post(headers)
            self.assertEqual(getattr(self.app.service, "shuo_calls", 0), 0)

            with post(
                {
                    "Origin": origin,
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Taoguba-Session-Token": self.app.session_token,
                }
            ) as response:
                self.assertEqual(response.status, 200)
            self.app.wait_for_idle(timeout=1)
            self.assertEqual(self.app.service.shuo_calls, 1)
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()

    def test_each_workspace_uses_a_distinct_ephemeral_session_token(self):
        other_app = WebApp(
            settings_store=SettingsStore(
                Path(self.temp_dir.name) / "other-settings.json"
            ),
            service=FakeService(),
            profile_dir=Path(self.temp_dir.name) / "other-profile",
        )

        self.assertGreaterEqual(len(self.app.session_token), 32)
        self.assertNotEqual(self.app.session_token, other_app.session_token)
        self.assertNotIn("session_token", self.app.state())

    def test_shuo_worker_reservation_is_atomic(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )
        shuo_url = (
            "https://shuo.tgb.cn/shuo/toViewShuo?"
            "shuoID=2079570335635705862"
        )
        callers_ready = threading.Barrier(2)
        original_options = self.app._options

        def synchronized_options(*, require_output=True):
            options = original_options(require_output=require_output)
            callers_ready.wait(timeout=1)
            return options

        self.app._options = synchronized_options
        self.app.service.shuo_started = threading.Event()
        self.app.service.shuo_release = threading.Event()
        outcomes = []

        def start():
            try:
                self.app.start_shuo(shuo_url)
                outcomes.append("started")
            except RuntimeError:
                outcomes.append("rejected")

        callers = [threading.Thread(target=start) for _ in range(2)]
        for caller in callers:
            caller.start()
        for caller in callers:
            caller.join(timeout=2)

        self.assertEqual(sorted(outcomes), ["rejected", "started"])
        self.assertTrue(self.app.service.shuo_started.wait(timeout=1))
        self.assertEqual(self.app.service.shuo_calls, 1)
        self.app.service.shuo_release.set()
        self.app.wait_for_idle(timeout=1)

    def test_shuo_is_rejected_and_disabled_while_login_is_pending(self):
        self.app.update_settings(
            {
                "output_dir": str(Path(self.temp_dir.name) / "exports"),
                "export_html": True,
                "export_markdown": False,
                "markdown_image_mode": None,
                "include_author_replies": False,
            }
        )
        self.app.service.login_started = threading.Event()
        self.app.start_login()
        self.assertTrue(self.app.service.login_started.wait(timeout=1))

        with self.assertRaisesRegex(RuntimeError, "登录"):
            self.app.start_shuo(
                "https://shuo.tgb.cn/shuo/toViewShuo?"
                "shuoID=2079570335635705862"
            )

        self.app.confirm_login()
        self.app._login_worker.join(timeout=1)

    def test_shuo_clears_stale_cancellation_and_cannot_be_stopped(self):
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
        stale_cancellation = self.app._cancellation
        self.app.service.shuo_started = threading.Event()
        self.app.service.shuo_release = threading.Event()

        self.app.start_shuo(
            "https://shuo.tgb.cn/shuo/toViewShuo?"
            "shuoID=2079570335635705862"
        )
        self.assertTrue(self.app.service.shuo_started.wait(timeout=1))

        self.assertIsNone(self.app._cancellation)
        self.assertFalse(self.app.state()["can_cancel"])
        with self.assertRaisesRegex(RuntimeError, "不支持停止"):
            self.app.cancel()
        self.assertFalse(stale_cancellation.is_cancelled())

        self.app.service.shuo_release.set()
        self.app.wait_for_idle(timeout=1)

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
            self.assertIn("/api/shuo", page)
            self.assertIn('id="replyFeed"', page)
            self.assertIn('id="replyDate" type="date"', page)
            self.assertIn('id="shuoUrl"', page)
            self.assertIn("X-Taoguba-Session-Token", page)
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
            self.assertIn("state.busy||state.login_pending", page)
            self.assertIn("$('stop').hidden=!state.can_cancel", page)
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
