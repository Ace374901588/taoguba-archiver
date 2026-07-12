import tempfile
import unittest
from pathlib import Path

from taoguba_archiver.core import parse_article
from taoguba_archiver.markdown import render_article_markdown


HTML = """
<html><body>
  <h1>测试标题</h1>
  <div id="first" class="article-text p_coten">
    <h2>小节</h2>
    <p>正文有<strong>重点</strong>和<a href="/a/linked">链接</a>。</p>
    <blockquote>引用内容</blockquote>
    <ul><li>项目一</li><li>项目二</li></ul>
    <img data-original="//image.tgb.cn/example.png" alt="示例图">
  </div>
</body></html>
"""


class MarkdownTests(unittest.TestCase):
    def test_renders_structure_and_relative_downloaded_image(self):
        article = parse_article(HTML, "https://www.tgb.cn/a/example")
        markdown = render_article_markdown(
            article,
            "https://www.tgb.cn/a/example",
            [
                {
                    "source_url": "https://image.tgb.cn/example.png",
                    "local_file": "images/example.png",
                }
            ],
            image_mode="relative",
        )

        self.assertIn("# 测试标题", markdown)
        self.assertIn("## 小节", markdown)
        self.assertIn("**重点**", markdown)
        self.assertIn("[链接](https://www.tgb.cn/a/linked)", markdown)
        self.assertIn("> 引用内容", markdown)
        self.assertIn("- 项目一", markdown)
        self.assertIn("![示例图](images/example.png)", markdown)

    def test_can_keep_source_image_urls(self):
        article = parse_article(HTML, "https://www.tgb.cn/a/example")
        markdown = render_article_markdown(
            article,
            "https://www.tgb.cn/a/example",
            [],
            image_mode="source",
        )
        self.assertIn("![示例图](https://image.tgb.cn/example.png)", markdown)

    def test_can_embed_downloaded_image(self):
        article = parse_article(HTML, "https://www.tgb.cn/a/example")
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = Path(temp_dir)
            images_dir = archive_dir / "images"
            images_dir.mkdir()
            (images_dir / "example.png").write_bytes(b"png-bytes")
            markdown = render_article_markdown(
                article,
                "https://www.tgb.cn/a/example",
                [
                    {
                        "source_url": "https://image.tgb.cn/example.png",
                        "local_file": "images/example.png",
                        "content_type": "image/png",
                    }
                ],
                image_mode="embed",
                archive_dir=archive_dir,
            )
        self.assertIn("data:image/png;base64,cG5nLWJ5dGVz", markdown)

    def test_rejects_unknown_mode_and_embed_without_archive(self):
        article = parse_article(HTML, "https://www.tgb.cn/a/example")
        with self.assertRaises(ValueError):
            render_article_markdown(article, "https://www.tgb.cn/a/example", [], image_mode="other")
        with self.assertRaises(ValueError):
            render_article_markdown(article, "https://www.tgb.cn/a/example", [], image_mode="embed")


if __name__ == "__main__":
    unittest.main()
