import unittest

from taoguba_archiver.daily_replies import (
    DailyReplyDetail,
    LatestReplyEntry,
    curate_daily_replies,
    parse_associated_reply,
    parse_latest_reply_feed,
    resolve_quote_image_placeholder,
    render_daily_replies_html,
    validate_reply_feed_url,
)


def make_detail(text: str, index: int) -> DailyReplyDetail:
    entry = LatestReplyEntry(
        published_at=f"2026-07-21 22:{index:02d}",
        text=text,
        article_title="测试主帖",
        article_url="https://www.tgb.cn/a/article-one",
        reply_url=f"https://www.tgb.cn/a/article-one/{index}#{index}",
    )
    return DailyReplyDetail(entry, text, f"<p>{text}</p>", None, [])


FEED_HTML = """
<html><body>
  <h1>测试作者的博客</h1>
  <section class="reply-item">
    <span class="reply-time">2026-07-21 22:16 跟帖了</span>
    <span>来自：《<a href="/a/article-one">测试主帖</a>》</span>
    <a href="/a/article-one/101#101">这是当天的跟帖 (26)</a>
  </section>
  <section class="reply-item">
    <span class="reply-time">2026-07-20 21:00 跟帖了</span>
    <span>来自：《<a href="/a/article-one">测试主帖</a>》</span>
    <a href="/a/article-one/100#100">这是前一天的跟帖 (8)</a>
  </section>
</body></html>
"""


ARTICLE_HTML = """
<html><body>
  <div class="comment-data user_42" id="reply_42_6">
    <div class="comment-data-user"><a href="/blog/42">测试作者</a></div>
    <time>2026-07-21 22:16</time>
    <div class="comment-data-text"><span class="span_101">这是当天的跟帖</span><img data-original="/image/reply.png"></div>
    <div class="comment-data-quote">
      <div class="quote-content">
      <a href="/blog/99">提问用户</a><time>2026-07-21 21:59</time>
      <p>这是被回复的原话。</p>
      </div>
    </div>
  </div>
</body></html>
"""


QUOTE_WITH_IMAGE_PLACEHOLDER_HTML = """
<html><body>
  <div class="comment-data user_42" id="reply_42_7">
    <time>2026-07-21 22:17</time>
    <div class="comment-data-text"><span class="span_102">回复了带图评论</span></div>
    <div class="comment-data-quote"><a href="/blog/99">提问用户</a>
      <time>2026-07-21 21:59</time><p>这是被回复的原话。［图片］</p></div>
  </div>
</body></html>
"""


ORIGINAL_COMMENT_WITH_IMAGE_HTML = """
<html><body>
  <div class="comment-data user_99" id="reply_99_1">
    <div class="comment-data-user"><a href="/blog/99">提问用户</a></div>
    <time>2026-07-21 21:59</time>
    <div class="comment-data-text"><p>这是被回复的原话。</p>
      <img src2="https://image.tgb.cn/original.png" src="/placeHolder.png"></div>
  </div>
</body></html>
"""


class LatestReplyFeedTests(unittest.TestCase):
    def test_curates_only_high_confidence_low_value_replies(self):
        details = [
            make_detail("收到", 1),
            make_detail("哈哈！！", 2),
            make_detail("600519 明天看承接", 3),
            make_detail("市场情绪感觉不太好", 4),
            make_detail("感谢", 5),
            make_detail("感谢", 6),
        ]

        result = curate_daily_replies(details)

        self.assertEqual(result.original_count, 6)
        self.assertEqual(result.automatic_filtered_count, 4)
        self.assertEqual(
            [item.text for item in result.details],
            ["600519 明天看承接", "市场情绪感觉不太好"],
        )

    def test_validates_only_explicit_latest_reply_feed_urls(self):
        self.assertEqual(
            validate_reply_feed_url(
                "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396"
            ),
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396",
        )
        with self.assertRaises(ValueError):
            validate_reply_feed_url("https://www.tgb.cn/blog/6671396")

    def test_parses_and_strictly_filters_reply_feed_entries(self):
        feed = parse_latest_reply_feed(
            FEED_HTML,
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=42",
        )

        self.assertEqual(feed.author, "测试作者")
        self.assertEqual(len(feed.entries), 2)
        self.assertEqual(feed.entries[0].published_at, "2026-07-21 22:16")
        self.assertEqual(feed.entries[0].article_title, "测试主帖")
        self.assertEqual(feed.entries[0].text, "这是当天的跟帖")
        self.assertEqual(
            feed.entries_for_date("2026-07-21")[0].reply_url,
            "https://www.tgb.cn/a/article-one/101#101",
        )

    def test_extracts_only_the_reply_context_embedded_with_target_comment(self):
        entry = parse_latest_reply_feed(
            FEED_HTML,
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=42",
        ).entries[0]

        detail = parse_associated_reply(
            ARTICLE_HTML,
            "https://www.tgb.cn/a/article-one/101#101",
            entry,
        )

        self.assertEqual(detail.text, "这是当天的跟帖")
        self.assertEqual(detail.context.author, "提问用户")
        self.assertEqual(detail.context.text, "这是被回复的原话。")
        self.assertEqual(detail.image_urls, ["https://www.tgb.cn/image/reply.png"])

    def test_renders_portable_daily_html_without_remote_images(self):
        entry = parse_latest_reply_feed(
            FEED_HTML,
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=42",
        ).entries[0]
        detail = parse_associated_reply(
            ARTICLE_HTML,
            "https://www.tgb.cn/a/article-one/101#101",
            entry,
        )

        html = render_daily_replies_html(
            "测试作者", "2026-07-21", [detail], {"https://www.tgb.cn/image/reply.png": "images/01.png"}
        )

        self.assertIn("测试作者 · 2026-07-21 跟帖整理", html)
        self.assertIn("这是被回复的原话。", html)
        self.assertIn('src="images/01.png"', html)
        self.assertNotIn("data-original", html)
        self.assertIn('class="timeline-item"', html)
        self.assertIn('class="timeline-rail"', html)
        self.assertIn('class="timeline-content"', html)
        self.assertIn(">22:16<", html)
        self.assertIn("width:min(100% - 48px,1440px)", html)
        self.assertIn("@media(max-width:720px)", html)

    def test_renders_context_author_and_time_only_in_the_summary_line(self):
        entry = parse_latest_reply_feed(
            FEED_HTML,
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=42",
        ).entries[0]
        detail = parse_associated_reply(
            ARTICLE_HTML,
            "https://www.tgb.cn/a/article-one/101#101",
            entry,
        )

        html = render_daily_replies_html(
            "测试作者", "2026-07-21", [detail],
            {"https://www.tgb.cn/image/reply.png": "images/01.png"},
        )

        self.assertEqual(html.count("提问用户"), 1)
        self.assertEqual(html.count("2026-07-21 21:59"), 1)
        self.assertIn("这是被回复的原话。", html)

    def test_recovers_original_image_for_a_quote_with_picture_placeholder(self):
        entry = parse_latest_reply_feed(
            FEED_HTML,
            "https://www.tgb.cn/user/blog/moreReplyMod?userID=42",
        ).entries[0]
        entry = entry.__class__(
            "2026-07-21 22:17", "回复了带图评论", entry.article_title,
            entry.article_url, "https://www.tgb.cn/a/article-one/102#102"
        )
        detail = parse_associated_reply(
            QUOTE_WITH_IMAGE_PLACEHOLDER_HTML, entry.reply_url, entry
        )

        self.assertTrue(detail.context.image_placeholder)
        recovered = resolve_quote_image_placeholder(
            ORIGINAL_COMMENT_WITH_IMAGE_HTML, entry.article_url, detail.context
        )

        self.assertEqual(recovered.image_urls, ["https://image.tgb.cn/original.png"])
        html = render_daily_replies_html(
            "测试作者", "2026-07-21", [detail.__class__(detail.entry, detail.text, detail.html, recovered, detail.image_urls)],
            {"https://image.tgb.cn/original.png": "images/original.png"},
        )
        self.assertIn('src="images/original.png"', html)
        self.assertNotIn("［图片］", html)

    def test_recovers_quote_image_when_the_original_comment_omits_a_readable_author_name(self):
        entry = parse_latest_reply_feed(
            FEED_HTML, "https://www.tgb.cn/user/blog/moreReplyMod?userID=42"
        ).entries[0]
        entry = entry.__class__(
            "2026-07-21 22:17", "回复了带图评论", entry.article_title,
            entry.article_url, "https://www.tgb.cn/a/article-one/102#102"
        )
        context = parse_associated_reply(
            QUOTE_WITH_IMAGE_PLACEHOLDER_HTML, entry.reply_url, entry
        ).context
        original_without_name = ORIGINAL_COMMENT_WITH_IMAGE_HTML.replace(
            '<div class="comment-data-user"><a href="/blog/99">提问用户</a></div>',
            '<a href="/blog/99"><img src="avatar.png"></a>',
        )

        recovered = resolve_quote_image_placeholder(
            original_without_name, entry.article_url, context
        )

        self.assertEqual(recovered.image_urls, ["https://image.tgb.cn/original.png"])
        self.assertEqual(recovered.author, "提问用户")


if __name__ == "__main__":
    unittest.main()
