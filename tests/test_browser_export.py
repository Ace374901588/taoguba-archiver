import json
import tempfile
import unittest
from pathlib import Path

from taoguba_archiver.browser import TaogubaBrowser


HTML = """
<html><head></head><body>
<h1>导出测试</h1>
<div class="article-data"><span class="data-userid"><a>归档作者</a></span><span>淘股吧原创 2026-07-12 09:30</span></div>
<div id="first" class="article-text p_coten"><p>正文。</p>
<img class="lazy article-image" data-original="https://image.tgb.cn/picture.png"
     onclick="opennewimg(this)" onload="javascript:compressImg(this, 460)"
     src="https://www.tgb.cn/placeHolder.png" src2="https://image.tgb.cn/picture_max.png" alt="图"></div>
</body></html>
"""

SHUO_HTML = """
<html><head></head><body>
<aside><img src="https://image.tgb.cn/avatar.png" alt="头像"></aside>
<main class="shuo-detail">
<h1 class="shuo-title">盘前记录</h1>
<div class="shuo-meta"><a class="shuo-author">测试作者</a>
<time class="shuo-time">2026-07-23 09:30</time></div>
<section class="shuo-content"><p>只保留这一段正文。</p>
<img data-original="https://image.tgb.cn/shuo-content.png"
     src="https://www.tgb.cn/placeHolder.png" alt="正文图"></section>
</main>
<section class="comments">不应导出的评论。</section>
</body></html>
"""

SHUO_URL = "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=2079570335635705862"

LATEST_REPLIES_HTML = """
<html><body><h1>测试作者的博客</h1><section class="reply-item">
<span>2026-07-21 22:16 跟帖了</span><span>来自：《<a href="/a/article-one">测试主帖</a>》</span>
<a href="/a/article-one/101#101">收到 (26)</a></section>
<section class="reply-item"><span>2026-07-21 22:17 跟帖了</span>
<span>来自：《<a href="/a/article-one">测试主帖</a>》</span>
<a href="/a/article-one/102#102">当天跟帖 (27)</a></section>
<section class="reply-item"><span>2026-07-21 22:18 跟帖了</span>
<span>来自：《<a href="/a/article-one">测试主帖</a>》</span>
<a href="/a/article-one/103#103">当天跟帖 (28)</a></section></body></html>
"""

REPLY_DETAIL_HTML = """
<html><body><div class="comment-data" data-comment-id="{comment_id}">
<div class="comment-data-text"><p>{text}</p><img data-original="https://image.tgb.cn/reply.png"></div>
<div class="comment-data-reply"><a href="/blog/99">提问用户</a><time>2026-07-21 21:59</time><p>关联原话。</p></div>
</div></body></html>
"""


class FakeResponse:
    status = 200
    headers = {"content-type": "text/html", "set-cookie": "must-not-export"}
    ok = True

    def __init__(self, url=None):
        self.url = url

    def body(self):
        return b"raw-response"


class FakeImageResponse(FakeResponse):
    headers = {"content-type": "image/png"}

    def body(self):
        return b"image-bytes"


class FakeRequest:
    def get(self, url, timeout):
        self.timeout = timeout
        return FakeImageResponse(url)


class FakeContext:
    def __init__(self):
        self.request = FakeRequest()


class FakePage:
    def __init__(self):
        self.url = "https://www.tgb.cn/a/example"

    def goto(self, url, **_kwargs):
        self.url = url
        return FakeResponse()

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def wait_for_timeout(self, _milliseconds):
        return None

    def content(self):
        return SHUO_HTML if self.url.startswith("https://shuo.tgb.cn/") else HTML


class ShuoContext(FakeContext):
    def __init__(self, page=None):
        super().__init__()
        self.pages = []
        self.page = page or FakePage()

    def new_page(self):
        return self.page

    def close(self):
        return None


class LatestRepliesPage:
    def __init__(self):
        self.url = ""
        self._content = ""

    def goto(self, url, **_kwargs):
        self.url = url
        if "moreReplyMod" in url:
            self._content = LATEST_REPLIES_HTML
        else:
            self._content = "".join(
                REPLY_DETAIL_HTML.format(
                    comment_id=comment_id,
                    text="收到" if comment_id == "101" else "当天跟帖",
                )
                for comment_id in ("101", "102", "103")
            )
        return FakeResponse()

    def wait_for_timeout(self, _milliseconds):
        return None

    def content(self):
        return self._content

    def locator(self, _selector):
        return type("NoNextPage", (), {"count": lambda _self: 0})()


class LatestRepliesContext(FakeContext):
    def __init__(self):
        super().__init__()
        self.pages = []
        self.page = LatestRepliesPage()

    def new_page(self):
        return self.page

    def close(self):
        return None


class BrowserExportTests(unittest.TestCase):
    def test_exports_one_shuo_with_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext()
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            self.assertTrue(result.complete)
            self.assertEqual(result.url, SHUO_URL)
            for relative_path in ("shuo.html", "response.html", "rendered.html", "images"):
                self.assertTrue((result.archive_dir / relative_path).exists())
            metadata_text = (result.archive_dir / "metadata.json").read_text(encoding="utf-8")
            metadata = json.loads(metadata_text)
            self.assertEqual(metadata["source_type"], "shuo")
            self.assertEqual(len(metadata["assets"]), 1)
            self.assertNotIn("set-cookie", metadata_text.lower())
            self.assertNotIn("must-not-export", metadata_text)
            exported_html = (result.archive_dir / "shuo.html").read_text(encoding="utf-8")
            self.assertIn("只保留这一段正文。", exported_html)
            self.assertIn("测试作者", exported_html)
            self.assertIn('src="images/', exported_html)
            self.assertNotIn("不应导出的评论。", exported_html)
            self.assertNotIn("avatar.png", exported_html)

    def test_marks_a_failed_shuo_response_incomplete_and_keeps_diagnostics(self):
        class BadResponse(FakeResponse):
            status = 502
            ok = False

            def body(self):
                return b"bad gateway"

        class BadShuoPage(FakePage):
            def goto(self, url, **kwargs):
                self.url = url
                return BadResponse()

            def content(self):
                return "<html><title>502 Bad Gateway</title><body>Bad Gateway</body></html>"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext(BadShuoPage())
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            self.assertFalse(result.complete)
            self.assertIn("HTTP 502", result.incomplete_reason)
            self.assertTrue((result.archive_dir / "response.html").is_file())
            self.assertTrue((result.archive_dir / "rendered.html").is_file())

    def test_rejects_an_out_of_scope_shuo_redirect_without_leaking_its_url(self):
        class RedirectPage(FakePage):
            def goto(self, url, **kwargs):
                self.url = f"{url}&token=redirect-secret#credential-fragment"
                return FakeResponse(url)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext(RedirectPage())
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            self.assertFalse(result.complete)
            self.assertIn("URL", result.incomplete_reason)
            self.assertEqual(context.request.__dict__, {})
            archive_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in result.archive_dir.iterdir()
                if path.is_file()
            )
            self.assertNotIn("redirect-secret", archive_text)
            self.assertNotIn("credential-fragment", archive_text)
            metadata = json.loads((result.archive_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["source_url"], SHUO_URL)
            self.assertIsNone(metadata["final_url"])

    def test_sanitizes_secrets_from_all_shuo_diagnostics_and_exports(self):
        secret_html = """
        <html><head>
        <meta name="csrf-token" content="secret-meta-token">
        <style>.x { background: url('https://example.test/a?token=secret-style-token') }</style>
        <script>document.cookie = 'secret-script-cookie'</script>
        </head><body>
        <input type="hidden" name="csrf_token" value="secret-input-token">
        <iframe src="https://example.test/frame?auth=secret-frame-token"></iframe>
        <h1 class="shuo-title">安全诊断</h1>
        <section class="shuo-content">
        <a href="https://example.test/path?token=secret-link-token#secret-fragment"
           onclick="send('secret-event-token')">正文链接</a>
        <p>https://example.test/plain?token=secret-text-token#plain-fragment</p>
        <p>token=plain-credential-value</p>
        <p>{"accessToken":"json-access-value","csrfToken":"json-csrf-value"}</p>
        <div data-state='{"authorization":"json-auth-value","cookie":"json-cookie-value",
          "session":"json-session-value","secret":"json-secret-value",
          "password":"json-password-value"}'>保留普通文字</div>
        <a href="https://example.test/private/accessToken/path-credential-value">路径凭据</a>
        <img data-original="https://image.tgb.cn/secure.png?token=secret-image-token">
        </section></body></html>
        """

        class SecretResponse(FakeResponse):
            def body(self):
                return secret_html.encode("utf-8")

        class SecretPage(FakePage):
            def goto(self, url, **kwargs):
                self.url = url
                return SecretResponse(url)

            def content(self):
                return secret_html

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext(SecretPage())
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            self.assertTrue(result.complete)
            combined = "\n".join(
                (result.archive_dir / filename).read_text(encoding="utf-8")
                for filename in ("response.html", "rendered.html", "shuo.html", "metadata.json")
            )
            for secret in (
                "accessToken",
                "csrfToken",
                "token=",
                "authorization",
                "cookie",
                "session",
                "secret",
                "password",
                "secret-meta-token",
                "secret-style-token",
                "secret-script-cookie",
                "secret-input-token",
                "secret-frame-token",
                "secret-link-token",
                "secret-fragment",
                "secret-event-token",
                "secret-text-token",
                "secret-image-token",
                "plain-credential-value",
                "json-access-value",
                "json-csrf-value",
                "json-auth-value",
                "json-cookie-value",
                "json-session-value",
                "json-secret-value",
                "json-password-value",
                "path-credential-value",
            ):
                self.assertNotIn(secret.lower(), combined.lower())

    def test_classifies_a_rejected_redirect_login_page_without_parsing_it(self):
        class LoginRedirectPage(FakePage):
            def goto(self, url, **kwargs):
                self.url = "https://login.tgb.cn/auth?token=redirect-login-secret"
                return FakeResponse(url)

            def content(self):
                return """
                <html><body><p>登录后可查看全文 token=redirect-page-secret</p>
                <section class="shuo-content"><p>越界正文不得解析。</p>
                <img src="https://image.tgb.cn/out-of-scope.png"></section>
                </body></html>
                """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext(LoginRedirectPage())
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            self.assertFalse(result.complete)
            self.assertTrue(result.login_required)
            self.assertIn("登录", result.incomplete_reason)
            self.assertEqual(context.request.__dict__, {})
            exported_html = (result.archive_dir / "shuo.html").read_text(encoding="utf-8")
            self.assertNotIn("越界正文不得解析。", exported_html)
            metadata = json.loads((result.archive_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(metadata["shuo"]["login_required"])
            self.assertNotIn(
                "redirect-page-secret",
                (result.archive_dir / "rendered.html").read_text(encoding="utf-8"),
            )

    def test_rejects_redirected_and_non_image_shuo_assets(self):
        shuo_with_two_images = SHUO_HTML.replace(
            "</section>",
            '<img src="https://image.tgb.cn/not-image.png" alt="伪图片"></section>',
            1,
        )

        class AssetResponse(FakeImageResponse):
            def __init__(self, url, content_type):
                super().__init__(url)
                self.headers = {"content-type": content_type}

        class UnsafeAssetRequest:
            def get(self, url, timeout):
                if url.endswith("shuo-content.png"):
                    return AssetResponse("https://evil.example/redirected.png", "image/png")
                return AssetResponse(url, "text/html")

        class TwoImagePage(FakePage):
            def content(self):
                return shuo_with_two_images

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext(TwoImagePage())
            context.request = UnsafeAssetRequest()
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            metadata = json.loads((result.archive_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(result.complete)
            self.assertEqual(len(metadata["assets"]), 2)
            self.assertTrue(all(asset["local_file"] is None for asset in metadata["assets"]))
            self.assertTrue(all(asset["error"] for asset in metadata["assets"]))
            self.assertEqual(list((result.archive_dir / "images").iterdir()), [])

    def test_navigation_error_creates_safe_incomplete_shuo_diagnostics(self):
        class NavigationErrorPage(FakePage):
            def goto(self, url, **kwargs):
                raise RuntimeError(f"navigation failed: {url}&token=navigation-secret")

            def content(self):
                raise AssertionError("content must not be read after failed navigation")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = ShuoContext(NavigationErrorPage())
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_shuo(SHUO_URL)

            self.assertFalse(result.complete)
            self.assertIn("导航失败", result.incomplete_reason)
            self.assertNotIn("navigation-secret", result.incomplete_reason)
            for filename in ("response.html", "rendered.html", "shuo.html", "metadata.json"):
                self.assertTrue((result.archive_dir / filename).is_file())
                self.assertNotIn(
                    "navigation-secret",
                    (result.archive_dir / filename).read_text(encoding="utf-8"),
                )

    def test_exports_explicit_latest_replies_as_a_portable_daily_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = LatestRepliesContext()
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_latest_replies(
                "https://www.tgb.cn/user/blog/moreReplyMod?userID=42", "2026-07-21"
            )

            self.assertTrue(result.complete)
            self.assertEqual(result.reply_count, 3)
            html = (result.archive_dir / "daily-replies.html").read_text(encoding="utf-8")
            metadata = json.loads((result.archive_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("关联原话。", html)
            self.assertIn('src="images/', html)
            self.assertIn("原始 3 条 · 自动筛除 2 条 · 当前保留 1 条", html)
            self.assertIn('data-original-count="3"', html)
            self.assertEqual(metadata["target_date"], "2026-07-21")
            self.assertEqual(metadata["original_reply_count"], 3)
            self.assertEqual(metadata["automatic_filtered_count"], 2)
            self.assertEqual(metadata["retained_reply_count"], 1)
            self.assertEqual(len(metadata["replies"]), 1)
            self.assertNotIn("cookie", json.dumps(metadata).lower())

    def test_marks_a_failed_reply_feed_response_incomplete_and_keeps_diagnostics(self):
        class BadResponse(FakeResponse):
            status = 502
            ok = False

            def body(self):
                return b"bad gateway"

        class BadPage(LatestRepliesPage):
            def goto(self, url, **kwargs):
                self.url = url
                self._content = "<html><title>502 Bad Gateway</title><body>Bad Gateway</body></html>"
                return BadResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = LatestRepliesContext()
            context.page = BadPage()
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_latest_replies(
                "https://www.tgb.cn/user/blog/moreReplyMod?userID=42", "2026-07-21"
            )

            self.assertFalse(result.complete)
            self.assertIn("HTTP 502", result.incomplete_reason)
            self.assertTrue((result.archive_dir / "response.html").is_file())
            self.assertTrue((result.archive_dir / "rendered.html").is_file())

    def test_reuses_the_same_dom_snapshot_when_a_live_page_changes_between_reads(self):
        class ChangingPage(LatestRepliesPage):
            def content(self):
                if "moreReplyMod" in self.url:
                    return self._content
                self.reads = getattr(self, "reads", 0) + 1
                return f"{self._content}<!-- live-render-{self.reads} -->"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", settle_ms=0)
            context = LatestRepliesContext()
            context.page = ChangingPage()
            browser._launch = lambda: (type("Manager", (), {"stop": lambda _self: None})(), context)

            result = browser.fetch_latest_replies(
                "https://www.tgb.cn/user/blog/moreReplyMod?userID=42", "2026-07-21"
            )

            self.assertTrue(result.complete)
            self.assertEqual(result.reply_count, 3)

    def test_markdown_only_keeps_traceability_files_and_safe_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(
                root / "profile",
                root / "exports",
                export_html=False,
                export_markdown=True,
                markdown_image_mode="relative",
                settle_ms=0,
            )
            archive, complete, reason, login_required = browser._fetch_one(
                FakeContext(), FakePage(), "https://www.tgb.cn/a/example"
            )

            self.assertTrue(complete)
            self.assertIsNone(reason)
            self.assertFalse(login_required)
            self.assertTrue((archive / "response.html").is_file())
            self.assertTrue((archive / "rendered.html").is_file())
            self.assertFalse((archive / "article-body.html").exists())
            self.assertTrue((archive / "article.md").is_file())
            self.assertIn("images/", (archive / "article.md").read_text(encoding="utf-8"))
            metadata_text = (archive / "metadata.json").read_text(encoding="utf-8")
            metadata = json.loads(metadata_text)
            self.assertEqual(metadata["schema_version"], 1)
            self.assertEqual(metadata["exports"]["markdown_image_mode"], "relative")
            self.assertNotIn("set-cookie", metadata_text.lower())
            self.assertNotIn("must-not-export", metadata_text)

    def test_html_and_markdown_can_be_written_together(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(
                root / "profile",
                root / "exports",
                export_html=True,
                export_markdown=True,
                markdown_image_mode="source",
                settle_ms=0,
            )
            archive, *_ = browser._fetch_one(
                FakeContext(), FakePage(), "https://www.tgb.cn/a/example"
            )
            self.assertTrue((archive / "article-body.html").is_file())
            self.assertTrue((archive / "article.md").is_file())
            exported_html = (archive / "article-body.html").read_text(encoding="utf-8")
            metadata = json.loads((archive / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("<!doctype html>", exported_html)
            self.assertIn('<html lang="zh-CN">', exported_html)
            self.assertIn("<title>导出测试 · 淘股吧文章归档器</title>", exported_html)
            self.assertIn('<main class="archive-page">', exported_html)
            self.assertIn('class="archive-article"', exported_html)
            self.assertIn("作者：归档作者", exported_html)
            self.assertIn("发布时间：2026-07-12 09:30", exported_html)
            self.assertIn('href="https://www.tgb.cn/a/example"', exported_html)
            self.assertIn('@media (max-width: 640px)', exported_html)
            self.assertIn(f'src="{metadata["assets"][0]["local_file"]}"', exported_html)
            self.assertIn('loading="lazy"', exported_html)
            self.assertNotIn("placeHolder.png", exported_html)
            self.assertNotIn("data-original", exported_html)
            self.assertNotIn("src2=", exported_html)
            self.assertNotIn("onclick=", exported_html)
            self.assertNotIn("onload=", exported_html)
            exported_markdown = (archive / "article.md").read_text(encoding="utf-8")
            self.assertIn("- 作者：归档作者", exported_markdown)
            self.assertIn("- 发布时间：2026-07-12 09:30", exported_markdown)


if __name__ == "__main__":
    unittest.main()
