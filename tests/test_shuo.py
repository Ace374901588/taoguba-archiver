import unittest

from taoguba_archiver.shuo import parse_shuo, render_shuo_html, validate_shuo_url


SHUO_HTML = """
<html><body>
  <main class="shuo-detail">
    <h1 class="shuo-title">盘前记录</h1>
    <div class="shuo-meta"><a class="shuo-author" href="/u/42">测试作者</a>
      <time class="shuo-time">2026-07-23 09:30</time></div>
    <section class="shuo-content"><p onclick="alert('x')">只保留这一段正文。</p>
      <img data-original="/images/content.png" src="/images/placeholder.png">
      <img src="/images/placeholder.png">
      <img src="https://css.tgb.cn/images/face/smile.gif">
      <script>alert('x')</script><iframe src="https://example.invalid"></iframe>
    </section>
  </main>
</body></html>
"""


class ShuoTests(unittest.TestCase):
    def test_validates_only_one_explicit_numeric_shuo_url(self):
        url = "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=2079570335635705862"
        self.assertEqual(validate_shuo_url(url), url)
        for invalid in (
            "http://shuo.tgb.cn/shuo/toViewShuo?shuoID=42",
            "https://www.tgb.cn/shuo/toViewShuo?shuoID=42",
            "https://shuo.tgb.cn/shuo/other?shuoID=42",
            "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=abc",
            "https://shuo.tgb.cn/shuo/toViewShuo",
        ):
            with self.subTest(url=invalid), self.assertRaises(ValueError):
                validate_shuo_url(invalid)

    def test_rejects_url_parts_that_could_carry_or_redirect_sensitive_state(self):
        for invalid in (
            "https://user@shuo.tgb.cn/shuo/toViewShuo?shuoID=42",
            "https://shuo.tgb.cn:444/shuo/toViewShuo?shuoID=42",
            "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42#profile",
            "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42&token=secret",
            "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42&shuoID=43",
        ):
            with self.subTest(url=invalid), self.assertRaises(ValueError):
                validate_shuo_url(invalid)

    def test_parses_only_the_shuo_body_and_its_content_image(self):
        content = parse_shuo(
            SHUO_HTML, "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"
        )

        self.assertEqual(content.title, "盘前记录")
        self.assertEqual(content.author, "测试作者")
        self.assertEqual(content.published_at, "2026-07-23 09:30")
        self.assertEqual(content.body_text, "只保留这一段正文。")
        self.assertEqual(content.image_urls, ["https://shuo.tgb.cn/images/content.png"])
        self.assertNotIn("onclick", content.body_html)
        self.assertNotIn("script", content.body_html)
        self.assertNotIn("iframe", content.body_html)

    def test_renders_portable_html_with_only_downloaded_images(self):
        content = parse_shuo(
            SHUO_HTML, "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42"
        )

        rendered = render_shuo_html(
            content,
            {"https://shuo.tgb.cn/images/content.png": "images/01.png"},
            "https://shuo.tgb.cn/shuo/toViewShuo?shuoID=42",
        )

        self.assertIn('src="images/01.png"', rendered)
        self.assertNotIn("data-original", rendered)
        self.assertNotIn("onclick", rendered)
        self.assertNotIn("placeholder.png", rendered)
        self.assertNotIn("css.tgb.cn", rendered)


if __name__ == "__main__":
    unittest.main()
