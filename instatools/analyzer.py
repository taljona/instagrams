"""
Instagram Hashtag & Profile Analyzer.

Analyze hashtag usage, top posts, related hashtags, and engagement metrics.
"""

import json
import re
import time
import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from instatools.utils import (
    create_session,
    retry,
    print_header,
    print_field,
    print_success,
    print_error,
    print_warning,
    print_info,
    export_json,
    generate_json_path,
    normalize_username,
    format_number,
    DEFAULT_DELAY,
)

logger = logging.getLogger("instatools")


class Analyzer:
    """Instagram hashtag and engagement analyzer.

    Usage:
        analyzer = Analyzer()
        stats = analyzer.analyze_hashtag("travel")
        profile_stats = analyzer.analyze_profile("natgeo")
    """

    HASHTAG_URL = "https://www.instagram.com/explore/tags/{tag}/?__a=1&__d=dis"
    WEB_HASHTAG_URL = "https://www.instagram.com/explore/tags/{tag}/"
    GRAPHQL_URL = "https://www.instagram.com/graphql/query/"
    TOP_POSTS_HASH = "17888483320059182"
    HASHTAG_SEARCH_HASH = "17875800861876929"

    def __init__(
        self,
        cookie: Optional[str] = None,
        delay: float = DEFAULT_DELAY,
    ):
        """Initialize the analyzer.

        Args:
            cookie: Optional Instagram session cookie.
            delay: Delay between requests in seconds.
        """
        self.session = create_session(cookie)
        self.delay = delay
        self._last_request_time = 0

    def _throttle(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    @retry()
    def _fetch_hashtag_data(self, tag: str) -> Dict[str, Any]:
        """Fetch hashtag data from Instagram's JSON endpoint.

        Args:
            tag: Hashtag name (without #).

        Returns:
            Raw hashtag data dictionary.
        """
        self._throttle()

        url = self.HASHTAG_URL.format(tag=tag)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()

        # Navigate the response structure
        if "graphql" in data:
            return data["graphql"].get("hashtag", {})
        elif "data" in data:
            return data["data"].get("hashtag", {})
        elif "hashtag" in data:
            return data["hashtag"]

        return data

    @retry()
    def _fetch_hashtag_html(self, tag: str) -> Dict[str, Any]:
        """Fallback: fetch hashtag data by parsing HTML.

        Args:
            tag: Hashtag name.

        Returns:
            Extracted hashtag data dictionary.
        """
        self._throttle()

        url = self.WEB_HASHTAG_URL.format(tag=tag)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract meta tags
        meta = {}
        for tg in soup.find_all("meta"):
            prop = tg.get("property") or tg.get("name", "")
            content = tg.get("content", "")
            if prop and content:
                meta[prop] = content

        # Try shared data
        shared_data = {}
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "window._sharedData" in script_text:
                try:
                    match = re.search(
                        r"window\._sharedData\s*=\s*({.*?});",
                        script_text,
                        re.DOTALL,
                    )
                    if match:
                        shared_data = json.loads(match.group(1))
                except (json.JSONDecodeError, AttributeError):
                    continue

        hashtag = {
            "name": tag,
            "media_count": 0,
            "description": meta.get("og:description", ""),
        }

        # Enrich from shared data
        if shared_data:
            hashtag_data = (
                shared_data.get("entry_data", {})
                .get("TagPage", [{}])[0]
                .get("graphql", {})
                .get("hashtag", {})
            )
            if hashtag_data:
                hashtag["name"] = hashtag_data.get("name", tag)
                hashtag["media_count"] = hashtag_data.get("edge_hashtag_to_media", {}).get("count", 0)

                # Get top posts
                edges = (
                    hashtag_data.get("edge_hashtag_to_media", {})
                    .get("edges", [])
                )
                hashtag["top_posts"] = [
                    {
                        "shortcode": e.get("node", {}).get("shortcode", ""),
                        "display_url": e.get("node", {}).get("display_url", ""),
                        "likes": e.get("node", {}).get("edge_liked_by", {}).get("count", 0),
                        "comments": e.get("node", {}).get("edge_media_to_comment", {}).get("count", 0),
                        "owner": e.get("node", {}).get("owner", {}).get("username", ""),
                    }
                    for e in edges
                ]

                # Related hashtags
                related = (
                    hashtag_data.get("edge_hashtag_to_related_tags", {})
                    .get("edges", [])
                )
                hashtag["related_tags"] = [
                    r.get("node", {}).get("name", "") for r in related
                ]

        return hashtag

    def analyze_hashtag(self, tag: str) -> Dict[str, Any]:
        """Analyze an Instagram hashtag.

        Args:
            tag: Hashtag name (with or without #).

        Returns:
            Dictionary with hashtag statistics including:
                - name, media_count
                - top_posts with engagement data
                - related_tags
                - avg_likes, avg_comments
        """
        # Clean the tag
        tag = tag.strip().lstrip("#").strip()
        print_header(f"Analyzing hashtag: #{tag}")

        # Try JSON endpoint first, then HTML fallback
        try:
            hashtag_data = self._fetch_hashtag_data(tag)
        except Exception as e:
            logger.warning(f"JSON endpoint failed ({e}), trying HTML fallback...")
            try:
                hashtag_data = self._fetch_hashtag_html(tag)
            except Exception as e2:
                print_error(f"Failed to analyze hashtag #{tag}: {e2}")
                raise

        # Build analysis
        analysis = self._build_analysis(hashtag_data, tag)
        self._display_analysis(analysis)

        return analysis

    def _build_analysis(self, data: Dict[str, Any], tag: str) -> Dict[str, Any]:
        """Build a complete hashtag analysis from raw data.

        Args:
            data: Raw hashtag data from Instagram.
            tag: Hashtag name.

        Returns:
            Structured analysis dictionary.
        """
        top_posts = data.get("top_posts", [])
        related_tags = data.get("related_tags", [])

        # Extract posts from GraphQL format if not already parsed
        if not top_posts and "edge_hashtag_to_media" in data:
            edges = data["edge_hashtag_to_media"].get("edges", [])
            top_posts = []
            for edge in edges:
                node = edge.get("node", {})
                post = {
                    "shortcode": node.get("shortcode", ""),
                    "display_url": node.get("display_url", ""),
                    "likes": node.get("edge_liked_by", {}).get("count", 0),
                    "comments": node.get("edge_media_to_comment", {}).get("count", 0),
                    "owner": node.get("owner", {}).get("username", ""),
                    "is_video": node.get("is_video", False),
                    "caption": "",
                }
                # Get caption
                caption_edges = (
                    node.get("edge_media_to_caption", {}).get("edges", [])
                )
                if caption_edges:
                    post["caption"] = caption_edges[0].get("node", {}).get("text", "")
                top_posts.append(post)

        # Extract related tags from GraphQL format
        if not related_tags and "edge_hashtag_to_related_tags" in data:
            edges = data["edge_hashtag_to_related_tags"].get("edges", [])
            related_tags = [e.get("node", {}).get("name", "") for e in edges]

        # Calculate engagement metrics
        total_likes = sum(p.get("likes", 0) for p in top_posts)
        total_comments = sum(p.get("comments", 0) for p in top_posts)
        post_count = len(top_posts)

        avg_likes = total_likes // post_count if post_count else 0
        avg_comments = total_comments // post_count if post_count else 0
        avg_engagement = avg_likes + avg_comments

        return {
            "tag": tag,
            "media_count": data.get("media_count", 0),
            "top_posts": top_posts,
            "related_tags": related_tags[:20],
            "metrics": {
                "posts_analyzed": post_count,
                "total_likes": total_likes,
                "total_comments": total_comments,
                "avg_likes": avg_likes,
                "avg_comments": avg_comments,
                "avg_engagement": avg_engagement,
            },
        }

    def _display_analysis(self, analysis: Dict[str, Any]) -> None:
        """Print formatted hashtag analysis to the terminal.

        Args:
            analysis: Analysis data dictionary.
        """
        tag = analysis["tag"]
        metrics = analysis["metrics"]

        print_field("Hashtag", f"#{tag}")
        print_field("Total Posts", format_number(analysis["media_count"]))
        print_field("Posts Analyzed", str(metrics["posts_analyzed"]))
        print()

        print_info("Engagement Metrics:")
        print_field("Avg Likes", format_number(metrics["avg_likes"]), indent=4)
        print_field("Avg Comments", format_number(metrics["avg_comments"]), indent=4)
        print_field("Avg Engagement", format_number(metrics["avg_engagement"]), indent=4)

        if analysis["top_posts"]:
            print()
            print_info("Top Posts:")
            for i, post in enumerate(analysis["top_posts"][:5], 1):
                shortcode = post.get("shortcode", "")
                likes = format_number(post.get("likes", 0))
                comments = format_number(post.get("comments", 0))
                owner = post.get("owner", "unknown")
                print(f"    {i}. @{owner} — {likes} likes, {comments} comments")
                print(f"       https://www.instagram.com/p/{shortcode}/")

        if analysis["related_tags"]:
            print()
            print_info(f"Related Tags: {', '.join(f'#{t}' for t in analysis['related_tags'][:10])}")

        print_success(f"Analysis complete for #{tag}")

    def analyze_profile(self, username: str) -> Dict[str, Any]:
        """Analyze a profile's engagement metrics from recent posts.

        Args:
            username: Instagram username.

        Returns:
            Dictionary with profile engagement analysis.
        """
        username = normalize_username(username)
        print_header(f"Analyzing profile: @{username}")

        # Import here to avoid circular imports
        from instatools.scraper import Scraper

        cookie_val = self.session.headers.get("Cookie")
        scraper = Scraper(cookie=str(cookie_val) if cookie_val else None, delay=self.delay)

        try:
            profile = scraper.get_profile(username)
            posts = scraper.get_recent_posts(username, count=20)
        except Exception as e:
            print_error(f"Failed to fetch profile data: {e}")
            raise

        # Calculate engagement metrics
        total_likes = sum(p.get("likes", 0) for p in posts)
        total_comments = sum(p.get("comments", 0) for p in posts)
        post_count = len(posts)

        avg_likes = total_likes // post_count if post_count else 0
        avg_comments = total_comments // post_count if post_count else 0
        engagement_rate = 0.0
        if profile.get("follower_count", 0) > 0:
            engagement_rate = (
                (avg_likes + avg_comments) / profile["follower_count"]
            ) * 100

        analysis = {
            "username": username,
            "full_name": profile.get("full_name", ""),
            "follower_count": profile.get("follower_count", 0),
            "following_count": profile.get("following_count", 0),
            "media_count": profile.get("media_count", 0),
            "is_verified": profile.get("is_verified", False),
            "posts_analyzed": post_count,
            "metrics": {
                "total_likes": total_likes,
                "total_comments": total_comments,
                "avg_likes": avg_likes,
                "avg_comments": avg_comments,
                "engagement_rate": round(engagement_rate, 2),
            },
            "top_posts": sorted(
                posts,
                key=lambda p: p.get("likes", 0) + p.get("comments", 0),
                reverse=True,
            )[:5],
        }

        self._display_profile_analysis(analysis)
        return analysis

    def _display_profile_analysis(self, analysis: Dict[str, Any]) -> None:
        """Print formatted profile analysis.

        Args:
            analysis: Profile analysis data.
        """
        metrics = analysis["metrics"]

        print_field("Username", f"@{analysis['username']}")
        print_field("Full Name", analysis.get("full_name", ""))
        print_field("Followers", format_number(analysis["follower_count"]))
        print_field("Posts", format_number(analysis["media_count"]))
        print_field("Verified", "✓" if analysis.get("is_verified") else "No")
        print()

        print_info("Engagement Metrics (based on recent posts):")
        print_field("Avg Likes", format_number(metrics["avg_likes"]), indent=4)
        print_field("Avg Comments", format_number(metrics["avg_comments"]), indent=4)
        print_field("Engagement Rate", f"{metrics['engagement_rate']}%", indent=4)

        if analysis["top_posts"]:
            print()
            print_info("Top Performing Posts:")
            for i, post in enumerate(analysis["top_posts"], 1):
                likes = format_number(post.get("likes", 0))
                comments = format_number(post.get("comments", 0))
                shortcode = post.get("shortcode", "")
                print(f"    {i}. {likes} likes, {comments} comments")
                print(f"       https://www.instagram.com/p/{shortcode}/")

        print_success(f"Profile analysis complete for @{analysis['username']}")



