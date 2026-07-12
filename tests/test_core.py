import tempfile
import unittest
from pathlib import Path

from taoguba_archiver.core import (
    allocate_archive_dir,
    article_key_from_url,
    parse_article,
    validate_article_url,
)


ARTICLE_HTML = """
<!doctype html>
<html>
<head>
  <meta property="og:author" content="测试作者">
  <meta property="article:published_time" content="2026-07-10 12:30:00">
</head>
<body>
  <div id="stockTitle">一篇测试文章</div>
  <div id="first" class="article-text p_coten">
    <p>第一段。</p><p>第二段。</p>
    <img data-original="//image.tgb.cn/example.jpg">
  </div>
  <div class="comment-data">
    <div class="comment-data-user"><span>楼主</span></div>
    <div class="comment-data-text"><p>楼主补充。</p></div>
  </div>
  <div class="comment-data">
    <div class="comment-data-user"><span>访客</span></div>
    <div class="comment-data-text"><p>普通回复。</p></div>
  </div>
</body>
</html>
"""


class UrlTests(unittest.TestCase):
    def test_accepts_supported_tgb_urls(self):
        self.assertEqual(
            validate_article_url("https://www.tgb.cn/a/2q0ojRLgHov-1"),
            "https://www.tgb.cn/a/2q0ojRLgHov-1",
        )
        self.assertEqual(
            validate_article_url("https://tgb.cn/Article/5688093/1"),
            "https://tgb.cn/Article/5688093/1",
        )

    def test_rejects_non_https_and_lookalike_hosts(self):
        for url in (
            "http://www.tgb.cn/a/abc",
            "https://evil.example/a/abc",
            "https://www.tgb.cn.evil.example/a/abc",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_article_url(url)

    def test_derives_stable_article_key(self):
        self.assertEqual(
            article_key_from_url("https://www.tgb.cn/a/2q0ojRLgHov-1"), "2q0ojRLgHov-1"
        )
        self.assertEqual(article_key_from_url("https://www.tgb.cn/Article/5688093/1"), "5688093-1")


class ParserTests(unittest.TestCase):
    def test_extracts_only_main_post_by_default(self):
        article = parse_article(ARTICLE_HTML, "https://www.tgb.cn/a/example")

        self.assertEqual(article.title, "一篇测试文章")
        self.assertEqual(article.author, "测试作者")
        self.assertEqual(article.published_at, "2026-07-10 12:30:00")
        self.assertEqual(article.main_text, "第一段。\n第二段。")
        self.assertEqual(article.author_replies, [])
        self.assertEqual(article.image_urls, ["https://image.tgb.cn/example.jpg"])
        self.assertFalse(article.login_required)

    def test_extracts_author_and_published_time_from_current_article_header(self):
        article = parse_article(
            """
            <div id="stockTitle">新版页面文章</div>
            <div class="article-data">
              <span class="data-userid"><a href="/blog/123">当前作者</a></span>
              <span>淘股吧原创&nbsp;2026-07-12 09:30&nbsp;</span>
            </div>
            <div id="first" class="article-text p_coten"><p>正文。</p></div>
            """,
            "https://www.tgb.cn/a/example",
        )

        self.assertEqual(article.author, "当前作者")
        self.assertEqual(article.published_at, "2026-07-12 09:30")

    def test_can_optionally_include_author_replies(self):
        article = parse_article(
            ARTICLE_HTML,
            "https://www.tgb.cn/a/example",
            include_author_replies=True,
        )

        self.assertEqual(article.author_replies, ["楼主补充。"])

    def test_marks_login_truncation(self):
        article = parse_article(
            "<html><body><h1>标题</h1><p>登录可查看全文</p></body></html>",
            "https://www.tgb.cn/a/example",
        )
        self.assertTrue(article.login_required)
        self.assertEqual(article.main_text, "")


class ArchiveTests(unittest.TestCase):
    def test_never_reuses_existing_archive_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = allocate_archive_dir(root, "abc", "文章标题", now="2026-07-11-101010")
            first.mkdir(parents=True)
            second = allocate_archive_dir(root, "abc", "文章标题", now="2026-07-11-101010")

            self.assertNotEqual(first, second)
            self.assertTrue(second.name.endswith("-2"))


if __name__ == "__main__":
    unittest.main()
