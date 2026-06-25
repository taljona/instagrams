"""
insta-tools — Instagram Toolkit CLI.

Main command-line interface for scraping profiles, downloading posts,
viewing stories, analyzing hashtags, and bulk operations.
"""

import argparse
import os
import sys
import logging

from instatools import __version__
from instatools.utils import setup_logging, print_info, print_error

logger = logging.getLogger("instatools")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands.

    Returns:
        Configured argparse.ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="instatools",
        description=(
            "📸 insta-tools — Instagram Toolkit\n"
            "Scrape profiles, download posts & stories, analyze hashtags.\n"
            "No API key needed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  instatools profile natgeo\n"
            "  instatools download 'https://www.instagram.com/p/CxYzAbCdEfG/'\n"
            "  instatools stories natgeo\n"
            "  instatools hashtag travel\n"
            "  instatools bulk urls.txt\n"
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"insta-tools {__version__}",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Export results to JSON file",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./downloads",
        help="Download directory (default: ./downloads)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2)",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help="Instagram session cookie for authenticated access",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress colored output",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="Available commands",
    )

    # ── profile ──────────────────────────────────────────────────────────
    profile_parser = subparsers.add_parser(
        "profile",
        help="Scrape an Instagram profile",
        description="Scrape public profile data: bio, followers, following, posts, etc.",
    )
    profile_parser.add_argument(
        "username",
        help="Instagram username (without @)",
    )
    profile_parser.add_argument(
        "--posts",
        action="store_true",
        help="Include recent posts in the output",
    )

    # ── download ─────────────────────────────────────────────────────────
    download_parser = subparsers.add_parser(
        "download",
        help="Download media from an Instagram post",
        description="Download images/videos from an Instagram post URL.",
    )
    download_parser.add_argument(
        "url",
        help="Instagram post URL or shortcode",
    )

    # ── stories ──────────────────────────────────────────────────────────
    stories_parser = subparsers.add_parser(
        "stories",
        help="View/download stories from a profile",
        description="Download active stories from a public Instagram profile.",
    )
    stories_parser.add_argument(
        "username",
        help="Instagram username (without @)",
    )

    # ── hashtag ──────────────────────────────────────────────────────────
    hashtag_parser = subparsers.add_parser(
        "hashtag",
        help="Analyze an Instagram hashtag",
        description="Analyze hashtag usage, top posts, related tags, and engagement.",
    )
    hashtag_parser.add_argument(
        "tag",
        help="Hashtag name (with or without #)",
    )

    # ── bulk ─────────────────────────────────────────────────────────────
    bulk_parser = subparsers.add_parser(
        "bulk",
        help="Bulk download from a file of URLs",
        description="Download multiple posts from a text file with one URL per line.",
    )
    bulk_parser.add_argument(
        "file",
        help="Path to text file with Instagram URLs (one per line)",
    )

    return parser


def cmd_profile(args: argparse.Namespace) -> None:
    """Execute the profile command."""
    from instatools.scraper import Scraper

    scraper = Scraper(cookie=args.cookie, delay=args.delay)

    if args.json:
        scraper.scrape_and_export(
            args.username,
            output_dir=args.output_dir,
            include_posts=True,
        )
    else:
        scraper.get_profile(args.username)
        if args.posts:
            posts = scraper.get_recent_posts(args.username)
            print_info(f"\nRecent posts ({len(posts)}):")
            for i, post in enumerate(posts, 1):
                from instatools.utils import format_number
                likes = format_number(post["likes"])
                comments = format_number(post["comments"])
                print(
                    f"  {i}. {likes} likes, {comments} comments — "
                    f"{post['url']}"
                )


def cmd_download(args: argparse.Namespace) -> None:
    """Execute the download command."""
    from instatools.downloader import Downloader

    dl = Downloader(
        cookie=args.cookie,
        output_dir=args.output_dir,
        delay=args.delay,
    )
    dl.download_post(args.url)


def cmd_stories(args: argparse.Namespace) -> None:
    """Execute the stories command."""
    from instatools.downloader import Downloader

    dl = Downloader(
        cookie=args.cookie,
        output_dir=args.output_dir,
        delay=args.delay,
    )
    dl.download_stories(args.username)


def cmd_hashtag(args: argparse.Namespace) -> None:
    """Execute the hashtag command."""
    from instatools.analyzer import Analyzer

    analyzer = Analyzer(cookie=args.cookie, delay=args.delay)

    if args.json:
        analysis = analyzer.analyze_hashtag(args.tag)
        from instatools.utils import export_json, generate_json_path

        filepath = generate_json_path(f"hashtag_{args.tag.lstrip('#')}", args.output_dir)
        export_json(analysis, filepath)
        print_info(f"Results exported to {filepath}")
    else:
        analyzer.analyze_hashtag(args.tag)


def cmd_bulk(args: argparse.Namespace) -> None:
    """Execute the bulk download command."""
    from instatools.downloader import Downloader

    dl = Downloader(
        cookie=args.cookie,
        output_dir=args.output_dir,
        delay=args.delay,
    )
    dl.bulk_download_from_file(args.file)


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(quiet=args.quiet)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Command dispatch
    commands = {
        "profile": cmd_profile,
        "download": cmd_download,
        "stories": cmd_stories,
        "hashtag": cmd_hashtag,
        "bulk": cmd_bulk,
    }

    handler = commands.get(args.command)
    if not handler:
        print_error(f"Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except KeyboardInterrupt:
        print_info("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Error: {e}")
        logger.debug("Traceback:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
