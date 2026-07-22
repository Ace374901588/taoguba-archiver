from __future__ import annotations

import argparse
import sys
from pathlib import Path

from platformdirs import user_data_dir

from .service import ArchiveOptions, ArchiveService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用独立 Chrome 登录态归档指定淘股吧文章到通用导出目录"
    )
    parser.add_argument("urls", nargs="*", help="一个或多个淘股吧文章 URL")
    parser.add_argument("--shuo", help="明确提供的一条淘股吧说说 URL")
    parser.add_argument("--urls-file", type=Path, help="每行一个 URL 的 UTF-8 文本文件")
    parser.add_argument(
        "--reply-feed",
        help="明确提供的淘股吧个人页“最新跟帖”URL；按日期整理为独立 HTML",
    )
    parser.add_argument(
        "--reply-date", help="--reply-feed 的目标日期，格式 YYYY-MM-DD"
    )
    parser.add_argument(
        "--login", action="store_true", help="打开专用 Chrome Profile，手工登录一次"
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(user_data_dir("TaogubaArchiver", appauthor=False)) / "chrome-profile",
        help="专用 Chrome Profile 目录",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("exports"),
        help="通用导出目录，默认 ./exports",
    )
    parser.add_argument("--headless", action="store_true", help="无界面运行；首次登录不能使用")
    parser.add_argument(
        "--include-author-replies",
        action="store_true",
        help="额外解析楼主跟帖；默认只解析主帖正文",
    )
    parser.add_argument("--markdown", action="store_true", help="额外生成 Markdown 正文")
    parser.add_argument(
        "--markdown-images",
        choices=("relative", "source", "embed"),
        help="Markdown 图片方式：相对路径、原图 URL 或内嵌 data URI",
    )
    parser.add_argument("--no-html", action="store_true", help="不生成 article-body.html")
    parser.add_argument("--timeout", type=int, default=45, help="页面和资源超时秒数，默认 45")
    parser.add_argument("--settle-ms", type=int, default=1500, help="页面载入后的额外等待毫秒数")
    return parser


def _load_urls(args) -> list[str]:
    urls = list(args.urls)
    if args.urls_file:
        for line in args.urls_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return list(dict.fromkeys(urls))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.login and args.headless:
        parser.error("--login 不能和 --headless 同时使用")
    if args.shuo and args.login:
        parser.error("--shuo 不能与 --login 同时使用；请先单独完成登录")
    if args.shuo and (args.urls or args.urls_file):
        parser.error("--shuo 不能与文章 URL 或 --urls-file 同时使用")
    if args.shuo and args.reply_feed:
        parser.error("--shuo 不能与 --reply-feed 同时使用")
    if args.shuo and args.headless:
        parser.error("--shuo 需要有界面 Chrome；淘股吧会拒绝无界面请求")
    if args.shuo and (args.markdown or args.markdown_images or args.no_html):
        parser.error("--shuo 固定生成独立 HTML，不支持 Markdown、--markdown-images 或 --no-html")
    if args.shuo and args.include_author_replies:
        parser.error("--shuo 不支持 --include-author-replies")
    if not args.login and args.markdown and not args.markdown_images:
        parser.error("使用 --markdown 时必须同时指定 --markdown-images")
    if not args.login and args.markdown_images and not args.markdown:
        parser.error("--markdown-images 只能与 --markdown 一起使用")
    if not args.login and args.no_html and not args.markdown:
        parser.error("--no-html 只能在启用 --markdown 时使用")
    if args.reply_feed and (args.urls or args.urls_file):
        parser.error("--reply-feed 不能与文章 URL 或 --urls-file 同时使用")
    if args.reply_feed and not args.reply_date:
        parser.error("使用 --reply-feed 时必须指定 --reply-date")
    if args.reply_feed and args.headless:
        parser.error("--reply-feed 需要有界面 Chrome；淘股吧会拒绝无界面请求")
    if args.reply_feed and (args.markdown or args.no_html):
        parser.error("最新跟帖整理固定生成独立 HTML，不支持 Markdown 或 --no-html")

    options = ArchiveOptions(
        profile_dir=args.profile_dir,
        output_dir=args.output_dir,
        headless=args.headless,
        include_author_replies=args.include_author_replies,
        export_html=not args.no_html,
        export_markdown=args.markdown,
        markdown_image_mode=args.markdown_images,
        timeout_ms=args.timeout * 1000,
        settle_ms=args.settle_ms,
    )
    service = ArchiveService()

    if args.login:
        service.login(options)
        print(f"登录 Profile 已保存在：{options.profile_dir.expanduser().resolve()}")
        return 0

    if args.reply_feed:
        try:
            result = service.collect_latest_replies(args.reply_feed, args.reply_date, options)
        except (ValueError, RuntimeError) as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2
        print(f"已整理 {result.reply_count} 条跟帖：{result.archive_dir}")
        if not result.complete:
            print(f"整理不完整：{result.incomplete_reason}", file=sys.stderr)
            return 3
        return 0

    if args.shuo:
        try:
            result = service.archive_shuo(args.shuo, options)
        except (ValueError, RuntimeError) as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2
        print(f"已归档说说：{result.archive_dir}")
        if not result.complete:
            print(
                f"说说归档不完整：{result.incomplete_reason or '请查看 metadata.json'}",
                file=sys.stderr,
            )
            return 3
        return 0

    urls = _load_urls(args)
    if not urls:
        parser.error("请提供文章 URL、--urls-file、--shuo、--reply-feed 或 --login")

    try:
        result = service.archive(urls, options)
    except (ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130

    for archive in result.archives:
        print(f"已归档：{archive}")
    if result.had_incomplete:
        print(
            "至少一篇文章不完整；请查看 metadata.json，并确认专用 Profile 已登录。", file=sys.stderr
        )
        return 3
    return 0
