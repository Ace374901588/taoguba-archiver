import json
import tempfile
import unittest
from pathlib import Path

from taoguba_archiver.browser import TaogubaBrowser


HTML = """
<html><head><meta property="og:author" content="作者"></head><body>
<h1>导出测试</h1>
<div id="first" class="article-text p_coten"><p>正文。</p>
<img src="https://image.tgb.cn/picture.png" alt="图"></div>
</body></html>
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


class BrowserExportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
