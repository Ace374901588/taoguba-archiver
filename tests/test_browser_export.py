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

LATEST_REPLIES_HTML = """
<html><body><h1>测试作者的博客</h1><section class="reply-item">
<span>2026-07-21 22:16 跟帖了</span><span>来自：《<a href="/a/article-one">测试主帖</a>》</span>
<a href="/a/article-one/101#101">当天跟帖 (26)</a></section></body></html>
"""

REPLY_DETAIL_HTML = """
<html><body><div class="comment-data" data-comment-id="101">
<div class="comment-data-text"><p>当天跟帖</p><img data-original="https://image.tgb.cn/reply.png"></div>
<div class="comment-data-reply"><a href="/blog/99">提问用户</a><time>2026-07-21 21:59</time><p>关联原话。</p></div>
</div></body></html>
"""


class FakeResponse:
    status = 200
    headers = {"content-type": "text/html", "set-cookie": "must-not-export"}
    ok = True

    def body(self):
        return b"raw-response"


class FakeImageResponse(FakeResponse):
    headers = {"content-type": "image/png"}

    def body(self):
        return b"image-bytes"


class FakeRequest:
    def get(self, _url, timeout):
        self.timeout = timeout
        return FakeImageResponse()


class FakeContext:
    def __init__(self):
        self.request = FakeRequest()


class FakePage:
    url = "https://www.tgb.cn/a/example"

    def goto(self, _url, **_kwargs):
        return FakeResponse()

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def wait_for_timeout(self, _milliseconds):
        return None

    def content(self):
        return HTML


class LatestRepliesPage:
    def __init__(self):
        self.url = ""
        self._content = ""

    def goto(self, url, **_kwargs):
        self.url = url
        self._content = LATEST_REPLIES_HTML if "moreReplyMod" in url else REPLY_DETAIL_HTML
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
            self.assertEqual(result.reply_count, 1)
            html = (result.archive_dir / "daily-replies.html").read_text(encoding="utf-8")
            metadata = json.loads((result.archive_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("关联原话。", html)
            self.assertIn('src="images/', html)
            self.assertEqual(metadata["target_date"], "2026-07-21")
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
            self.assertEqual(result.reply_count, 1)

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
