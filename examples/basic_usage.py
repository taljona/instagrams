#!/usr/bin/env python3
"""
Basic usage examples for insta-tools.

This script demonstrates how to use insta-tools as a Python library.
"""

from instatools import Scraper, Downloader, Analyzer


def scrape_profile():
    """Example: Scrape an Instagram profile."""
    print("=" * 50)
    print("EXAMPLE: Scrape a Profile")
    print("=" * 50)

    scraper = Scraper()

    try:
        profile = scraper.get_profile("natgeo")

        print(f"\nUsername: @{profile['username']}")
        print(f"Name: {profile['full_name']}")
        print(f"Bio: {profile['biography'][:100]}...")
        print(f"Followers: {profile['follower_count']:,}")
        print(f"Following: {profile['following_count']:,}")
        print(f"Posts: {profile['media_count']:,}")
        print(f"Verified: {'✓' if profile['is_verified'] else '✗'}")

    except Exception as e:
        print(f"Error: {e}")


def download_post():
    """Example: Download an Instagram post."""
    print("\n" + "=" * 50)
    print("EXAMPLE: Download a Post")
    print("=" * 50)

    dl = Downloader(output_dir="./downloads")

    try:
        # Replace with an actual post URL
        path = dl.download_post("https://www.instagram.com/p/CxYzAbCdEfG/")
        print(f"\nDownloaded to: {path}")

    except Exception as e:
        print(f"Error: {e}")


def analyze_hashtag():
    """Example: Analyze a hashtag."""
    print("\n" + "=" * 50)
    print("EXAMPLE: Analyze a Hashtag")
    print("=" * 50)

    analyzer = Analyzer()

    try:
        stats = analyzer.analyze_hashtag("travel")

        print(f"\nHashtag: #{stats['tag']}")
        print(f"Total Posts: {stats['media_count']:,}")
        print(f"Avg Likes: {stats['metrics']['avg_likes']:,}")
        print(f"Avg Comments: {stats['metrics']['avg_comments']:,}")
        print(f"Related Tags: {', '.join(stats['related_tags'][:5])}")

    except Exception as e:
        print(f"Error: {e}")


def export_to_json():
    """Example: Scrape and export to JSON."""
    print("\n" + "=" * 50)
    print("EXAMPLE: Export to JSON")
    print("=" * 50)

    scraper = Scraper()

    try:
        filepath = scraper.scrape_and_export(
            "natgeo",
            output_dir="./output",
            include_posts=True,
        )
        print(f"\nExported to: {filepath}")

    except Exception as e:
        print(f"Error: {e}")


def bulk_download():
    """Example: Bulk download from a list."""
    print("\n" + "=" * 50)
    print("EXAMPLE: Bulk Download")
    print("=" * 50)

    dl = Downloader(output_dir="./downloads")

    # Example URLs (replace with real ones)
    urls = [
        "https://www.instagram.com/p/CxYzAbCdEfG/",
        "https://www.instagram.com/p/AbCdEfGhIjK/",
    ]

    try:
        paths = dl.bulk_download(urls)
        print(f"\nDownloaded {len(paths)} posts")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("📸 insta-tools — Python Usage Examples\n")

    # Run examples (each handles its own errors)
    scrape_profile()
    download_post()
    analyze_hashtag()
    export_to_json()
    bulk_download()

    print("\n" + "=" * 50)
    print("All examples complete!")
    print("=" * 50)
