"""
Instagram Profile Scraper.

Scrapes public Instagram profiles for username, bio, followers, following,
post count, profile picture URL, verified status, and recent posts.
"""

import json
import re
import time
import logging
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
    export_json,
    generate_json_path,
    normalize_username,
    format_number,
    DEFAULT_DELAY,
)

logger = logging.getLogger("instatools")


class Scraper:
    """Instagram profile scraper using web endpoints.

    Usage:
        scraper = Scraper()
        profile = scraper.get_profile("natgeo")
    """

    GRAPHQL_URL = "https://www.instagram.com/graphql/query/"
    PROFILE_URL = "https://www.instagram.com/{username}/?__a=1&__d=dis"
    WEB_PROFILE_URL = "https://www.instagram.com/{username}/"

    # GraphQL query hash for profile info (Instagram's built-in query)
    PROFILE_QUERY_HASH = "c9100bf9110dd6361671f113dd02e7d6"

    def __init__(
        self,
        cookie: Optional[str] = None,
        delay: float = DEFAULT_DELAY,
    ):
        """Initialize the scraper.

        Args:
            cookie: Optional Instagram session cookie for authenticated access.
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
    def _fetch_profile_data(self, username: str) -> Dict[str, Any]:
        """Fetch profile data from Instagram's web endpoint.

        Args:
            username: Instagram username (without @).

        Returns:
            Parsed JSON data from the profile endpoint.

        Raises:
            requests.RequestException: On network errors.
            ValueError: On invalid or private profiles.
        """
        self._throttle()

        url = self.PROFILE_URL.format(username=username)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()

        # Instagram wraps the data under a "graphql" or "user" key
        if "graphql" in data:
            user_data = data["graphql"].get("user", {})
        elif "user" in data:
            user_data = data["user"]
        elif "data" in data and "user" in data["data"]:
            user_data = data["data"]["user"]
        else:
            raise ValueError(f"No profile data found for '{username}'")

        if not user_data:
            raise ValueError(
                f"Profile '{username}' not found or is private"
            )

        return user_data

    @retry()
    def _fetch_profile_html(self, username: str) -> Dict[str, Any]:
        """Fallback: fetch profile data by parsing the HTML page.

        This works when the JSON endpoint is blocked or rate-limited.

        Args:
            username: Instagram username.

        Returns:
            Extracted profile data dictionary.
        """
        self._throttle()

        url = self.WEB_PROFILE_URL.format(username=username)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Try to extract meta tags
        meta = {}
        for tag in soup.find_all("meta"):
            prop = tag.get("property") or tag.get("name", "")
            content = tag.get("content", "")
            if prop and content:
                meta[prop] = content

        # Extract JSON-LD structured data
        json_ld = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                json_ld = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

        # Try to extract from shared data script
        shared_data = {}
        for script in soup.find_all("script"):
            if script.string and "window._sharedData" in (script.string or ""):
                try:
                    match = re.search(
                        r"window\._sharedData\s*=\s*({.*?});",
                        script.string,
                        re.DOTALL,
                    )
                    if match:
                        shared_data = json.loads(match.group(1))
                except (json.JSONDecodeError, AttributeError):
                    continue

        # Build profile from available data
        profile = {
            "username": username,
            "full_name": meta.get("og:title", "").replace(" on Instagram", "").strip(),
            "biography": meta.get("og:description", ""),
            "profile_pic_url": meta.get("og:image", ""),
            "is_private": False,
            "is_verified": False,
            "follower_count": 0,
            "following_count": 0,
            "media_count": 0,
            "external_url": "",
            "data_source": "html_parse",
        }

        # Enrich from shared data if available
        if shared_data:
            user = shared_data.get("entry_data", {}).get("ProfilePage", [{}])[0]
            if user:
                user_info = user.get("graphql", {}).get("user", {})
                if user_info:
                    profile["username"] = user_info.get("username", username)
                    profile["full_name"] = user_info.get("full_name", profile["full_name"])
                    profile["biography"] = user_info.get("biography", profile["biography"])
                    profile["follower_count"] = user_info.get("edge_followed_by", {}).get("count", 0)
                    profile["following_count"] = user_info.get("edge_follow", {}).get("count", 0)
                    profile["media_count"] = user_info.get("edge_owner_to_timeline_media", {}).get("count", 0)
                    profile["profile_pic_url"] = user_info.get("profile_pic_url_hd") or user_info.get("profile_pic_url", "")
                    profile["is_private"] = user_info.get("is_private", False)
                    profile["is_verified"] = user_info.get("is_verified", False)
                    profile["external_url"] = user_info.get("external_url", "")
                    profile["data_source"] = "shared_data"

        return profile

    def get_profile(self, username: str) -> Dict[str, Any]:
        """Scrape a public Instagram profile.

        Args:
            username: Instagram username (with or without @).

        Returns:
            Dictionary with profile information including:
                - username, full_name, biography
                - follower_count, following_count, media_count
                - profile_pic_url, is_verified, is_private
                - external_url
        """
        username = normalize_username(username)
        print_header(f"Scraping profile: @{username}")

        try:
            user_data = self._fetch_profile_data(username)
            profile = self._parse_graphql_user(user_data)
            profile["data_source"] = "graphql"
        except Exception as e:
            logger.warning(f"GraphQL endpoint failed ({e}), trying HTML fallback...")
            try:
                profile = self._fetch_profile_html(username)
            except Exception as e2:
                print_error(f"Failed to scrape @{username}: {e2}")
                raise

        self._display_profile(profile)
        return profile

    def _parse_graphql_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse GraphQL user data into a clean profile dict.

        Args:
            data: Raw GraphQL user data.

        Returns:
            Cleaned profile dictionary.
        """
        return {
            "username": data.get("username", ""),
            "full_name": data.get("full_name", ""),
            "biography": data.get("biography", ""),
            "profile_pic_url": data.get("profile_pic_url_hd") or data.get("profile_pic_url", ""),
            "is_private": data.get("is_private", False),
            "is_verified": data.get("is_verified", False),
            "follower_count": data.get("edge_followed_by", {}).get("count", 0),
            "following_count": data.get("edge_follow", {}).get("count", 0),
            "media_count": data.get("edge_owner_to_timeline_media", {}).get("count", 0),
            "external_url": data.get("external_url", ""),
            "fb_page_info": data.get("fb_page_info", {}),
        }

    def _display_profile(self, profile: Dict[str, Any]) -> None:
        """Print formatted profile information to the terminal.

        Args:
            profile: Profile data dictionary.
        """
        if profile.get("is_verified"):
            verified_badge = " ✓"
        else:
            verified_badge = ""

        print_field("Username", f"@{profile['username']}{verified_badge}")
        print_field("Full Name", profile["full_name"])
        print_field("Bio", profile.get("biography", "(empty)") or "(empty)")
        print_field("Posts", format_number(profile["media_count"]))
        print_field("Followers", format_number(profile["follower_count"]))
        print_field("Following", format_number(profile["following_count"]))

        if profile.get("external_url"):
            print_field("Website", profile["external_url"])

        if profile.get("is_private"):
            print_warning("This account is PRIVATE — limited data available")

        print_field("Profile Pic", profile.get("profile_pic_url", "N/A")[:80] + "...")
        print_success(f"Profile scraped successfully (source: {profile.get('data_source', 'unknown')})")

    def get_recent_posts(self, username: str, count: int = 12) -> List[Dict[str, Any]]:
        """Fetch recent posts from a profile.

        Args:
            username: Instagram username.
            count: Number of posts to fetch (max varies).

        Returns:
            List of post data dictionaries.
        """
        username = normalize_username(username)
        self._throttle()

        user_data = self._fetch_profile_data(username)
        edges = (
            user_data.get("edge_owner_to_timeline_media", {})
            .get("edges", [])
        )

        posts = []
        for edge in edges[:count]:
            node = edge.get("node", {})
            post = {
                "shortcode": node.get("shortcode", ""),
                "caption": (
                    node.get("edge_media_to_caption", {})
                    .get("edges", [{}])[0]
                    .get("node", {})
                    .get("text", "")
                ),
                "likes": node.get("edge_liked_by", {}).get("count", 0),
                "comments": node.get("edge_media_to_comment", {}).get("count", 0),
                "timestamp": node.get("taken_at_timestamp", 0),
                "is_video": node.get("is_video", False),
                "video_url": node.get("video_url", ""),
                "display_url": node.get("display_url", ""),
                "thumbnail_url": node.get("thumbnail_src", ""),
                "url": f"https://www.instagram.com/p/{node.get('shortcode', '')}/",
            }
            posts.append(post)

        logger.info(f"Fetched {len(posts)} recent posts from @{username}")
        return posts

    def scrape_and_export(
        self,
        username: str,
        output_dir: str = ".",
        include_posts: bool = False,
    ) -> str:
        """Scrape a profile and export results to JSON.

        Args:
            username: Instagram username.
            output_dir: Directory to save the JSON file.
            include_posts: Whether to include recent posts.

        Returns:
            Path to the exported JSON file.
        """
        profile = self.get_profile(username)

        if include_posts:
            try:
                profile["recent_posts"] = self.get_recent_posts(username)
            except Exception as e:
                logger.warning(f"Could not fetch recent posts: {e}")

        username_clean = normalize_username(username)
        filepath = generate_json_path(f"profile_{username_clean}", output_dir)
        export_json(profile, filepath)

        print_success(f"Profile data exported to {filepath}")
        return filepath
