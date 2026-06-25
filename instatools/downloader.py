"""
Instagram Post & Story Downloader.

Download images and videos from Instagram posts and stories.
Saves media files locally with full metadata.
"""

import os
import json
import time
import logging
from typing import Any, Dict, List, Optional

from tqdm import tqdm
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
    ensure_dir,
    extract_shortcode,
    normalize_username,
    get_download_path,
    DEFAULT_DELAY,
    DEFAULT_DOWNLOAD_DIR,
)

logger = logging.getLogger("instatools")


class Downloader:
    """Instagram post and story downloader.

    Usage:
        dl = Downloader()
        dl.download_post("https://www.instagram.com/p/CxYzAbCdEfG/")
        dl.download_stories("natgeo")
    """

    POST_URL = "https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
    STORIES_API = "https://www.instagram.com/api/v1/users/{user_id}/story/"
    WEB_POST_URL = "https://www.instagram.com/p/{shortcode}/"
    USER_INFO_URL = "https://www.instagram.com/{username}/?__a=1&__d=dis"

    def __init__(
        self,
        cookie: Optional[str] = None,
        output_dir: str = DEFAULT_DOWNLOAD_DIR,
        delay: float = DEFAULT_DELAY,
    ):
        """Initialize the downloader.

        Args:
            cookie: Optional Instagram session cookie.
            output_dir: Base directory for downloads.
            delay: Delay between requests in seconds.
        """
        self.session = create_session(cookie)
        self.output_dir = output_dir
        self.delay = delay
        self._last_request_time = 0

    def _throttle(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    @retry()
    def _fetch_post_data(self, shortcode: str) -> Dict[str, Any]:
        """Fetch post data from Instagram's JSON endpoint.

        Args:
            shortcode: Instagram post shortcode.

        Returns:
            Parsed post data dictionary.
        """
        self._throttle()

        url = self.POST_URL.format(shortcode=shortcode)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()

        # Navigate the nested JSON structure
        if "graphql" in data:
            media = data["graphql"].get("shortcode_media", {})
        elif "items" in data:
            media = data["items"][0] if data["items"] else {}
        else:
            # Try alternative path
            media = data.get("shortcode_media", data.get("data", {}).get("shortcode_media", {}))

        if not media:
            raise ValueError(f"No post data found for shortcode '{shortcode}'")

        return media

    @retry()
    def _fetch_post_from_html(self, shortcode: str) -> Dict[str, Any]:
        """Fallback: fetch post data by parsing the HTML page.

        Args:
            shortcode: Instagram post shortcode.

        Returns:
            Extracted post data dictionary.
        """
        self._throttle()

        url = self.WEB_POST_URL.format(shortcode=shortcode)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract meta tags
        meta = {}
        for tag in soup.find_all("meta"):
            prop = tag.get("property") or tag.get("name", "")
            content = tag.get("content", "")
            if prop and content:
                meta[prop] = content

        # Try to find the shared data
        shared_data = {}
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if "window._sharedData" in script_text:
                try:
                    import re
                    match = re.search(
                        r"window\._sharedData\s*=\s*({.*?});",
                        script_text,
                        re.DOTALL,
                    )
                    if match:
                        shared_data = json.loads(match.group(1))
                except (json.JSONDecodeError, AttributeError):
                    continue

        # Build post data from available sources
        post = {
            "shortcode": shortcode,
            "is_video": False,
            "display_url": meta.get("og:image", ""),
            "caption": meta.get("og:description", ""),
            "video_url": "",
            "owner": {"username": "", "full_name": ""},
        }

        # Enrich from shared data
        if shared_data:
            media = (
                shared_data.get("entry_data", {})
                .get("PostPage", [{}])[0]
                .get("graphql", {})
                .get("shortcode_media", {})
            )
            if media:
                post["shortcode"] = media.get("shortcode", shortcode)
                post["is_video"] = media.get("is_video", False)
                post["display_url"] = media.get("display_url", post["display_url"])
                post["video_url"] = media.get("video_url", "")
                post["owner"] = {
                    "username": media.get("owner", {}).get("username", ""),
                    "full_name": media.get("owner", {}).get("full_name", ""),
                }

                # Get caption
                caption_edges = (
                    media.get("edge_media_to_caption", {}).get("edges", [])
                )
                if caption_edges:
                    post["caption"] = caption_edges[0].get("node", {}).get("text", "")

        return post

    def download_post(self, url: str, output_dir: Optional[str] = None) -> str:
        """Download media from an Instagram post URL.

        Args:
            url: Instagram post URL or shortcode.
            output_dir: Custom output directory (optional).

        Returns:
            Path to the downloaded directory.
        """
        # Extract shortcode from URL or use as-is
        shortcode = extract_shortcode(url) or url.strip()

        print_header(f"Downloading post: {shortcode}")

        try:
            media = self._fetch_post_data(shortcode)
        except Exception as e:
            logger.warning(f"JSON endpoint failed ({e}), trying HTML fallback...")
            try:
                media = self._fetch_post_from_html(shortcode)
            except Exception as e2:
                print_error(f"Failed to fetch post data: {e2}")
                raise

        # Build post info
        post_info = self._parse_post_info(media, shortcode)
        owner_username = post_info.get("owner_username", "unknown")

        # Determine download path
        if output_dir:
            download_path = ensure_dir(os.path.join(output_dir, shortcode))
        else:
            user_dir = get_download_path(owner_username, self.output_dir)
            download_path = ensure_dir(os.path.join(user_dir, shortcode))

        print_field("Owner", f"@{owner_username}")
        print_field("Caption", (post_info["caption"] or "(no caption)")[:100])
        print_field("Likes", str(post_info["likes"]))
        print_field("Comments", str(post_info["comments"]))
        print_field("Video", "Yes" if post_info["is_video"] else "No")

        # Download media files
        downloaded_files = []
        media_urls = post_info.get("media_urls", [])

        for i, media_url in enumerate(media_urls):
            if not media_url:
                continue

            try:
                ext = ".mp4" if post_info["is_video"] else ".jpg"
                filename = f"{shortcode}_{i + 1}{ext}" if len(media_urls) > 1 else f"{shortcode}{ext}"
                filepath = os.path.join(download_path, filename)

                self._download_file(media_url, filepath)
                downloaded_files.append(filepath)
                print_success(f"Saved: {filepath}")

            except Exception as e:
                print_error(f"Failed to download media: {e}")

        # Save metadata
        metadata_path = os.path.join(download_path, "metadata.json")
        export_json(post_info, metadata_path)
        print_success(f"Metadata saved to {metadata_path}")

        print_info(f"Download complete → {download_path}")
        return download_path

    def _parse_post_info(self, media: Dict[str, Any], shortcode: str) -> Dict[str, Any]:
        """Parse post data into a clean info dictionary.

        Args:
            media: Raw media data from Instagram.
            shortcode: Post shortcode.

        Returns:
            Parsed post information.
        """
        # Get caption
        caption = ""
        if "edge_media_to_caption" in media:
            edges = media["edge_media_to_caption"].get("edges", [])
            if edges:
                caption = edges[0].get("node", {}).get("text", "")

        # Get owner info
        owner = media.get("owner", {})

        # Collect media URLs (image or video)
        media_urls = []

        if media.get("is_video"):
            if media.get("video_url"):
                media_urls.append(media["video_url"])
        else:
            # Image
            if media.get("display_url"):
                media_urls.append(media["display_url"])

        # For carousel/album posts, get sidecar items
        if media.get("__typename") == "GraphSidecar":
            edges = media.get("edge_sidecar_to_children", {}).get("edges", [])
            media_urls = []
            for edge in edges:
                node = edge.get("node", {})
                if node.get("is_video"):
                    media_urls.append(node.get("video_url", ""))
                else:
                    media_urls.append(node.get("display_url", ""))

        return {
            "shortcode": shortcode,
            "caption": caption,
            "likes": media.get("edge_liked_by", {}).get("count", 0),
            "comments": media.get("edge_media_to_comment", {}).get("count", 0),
            "timestamp": media.get("taken_at_timestamp", 0),
            "is_video": media.get("is_video", False),
            "media_urls": [u for u in media_urls if u],
            "owner_username": owner.get("username", ""),
            "owner_full_name": owner.get("full_name", ""),
            "owner_is_verified": owner.get("is_verified", False),
            "location": media.get("location", {}).get("name", "") if media.get("location") else "",
            "url": f"https://www.instagram.com/p/{shortcode}/",
        }

    def _download_file(self, url: str, filepath: str) -> None:
        """Download a file from URL to disk with progress bar.

        Args:
            url: URL to download from.
            filepath: Local path to save the file.
        """
        self._throttle()

        response = self.session.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        ensure_dir(os.path.dirname(filepath))

        with open(filepath, "wb") as f:
            if total_size > 0:
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=os.path.basename(filepath),
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

    @retry()
    def _fetch_user_id(self, username: str) -> Optional[str]:
        """Fetch a user's internal ID (needed for stories API).

        Args:
            username: Instagram username.

        Returns:
            User ID string or None.
        """
        self._throttle()

        url = self.USER_INFO_URL.format(username=username)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()

        if "graphql" in data:
            user = data["graphql"].get("user", {})
        elif "data" in data and "user" in data["data"]:
            user = data["data"]["user"]
        else:
            user = data.get("user", {})

        return str(user.get("id", "")) if user else None

    @retry()
    def _fetch_stories(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetch stories for a user.

        Args:
            user_id: Instagram user ID.

        Returns:
            List of story data dictionaries.
        """
        self._throttle()

        url = self.STORIES_API.format(user_id=user_id)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()
        return data.get("items", [])

    def download_stories(
        self,
        username: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """View and download stories from a public profile.

        Args:
            username: Instagram username.
            output_dir: Custom output directory.

        Returns:
            Path to the stories download directory.
        """
        username = normalize_username(username)
        print_header(f"Fetching stories for @{username}")

        # Get user ID
        user_id = self._fetch_user_id(username)
        if not user_id:
            print_error(f"Could not find user ID for @{username}")
            print_warning("The user may not exist or the profile may be private")
            return ""

        print_info(f"User ID: {user_id}")

        # Fetch stories
        try:
            stories = self._fetch_stories(user_id)
        except Exception as e:
            print_error(f"Failed to fetch stories: {e}")
            print_warning(
                "Story access may require authentication. "
                "Try providing a session cookie with --cookie."
            )
            return ""

        if not stories:
            print_warning(f"@{username} has no active stories")
            return ""

        print_info(f"Found {len(stories)} story items")

        # Determine download path
        if output_dir:
            download_path = ensure_dir(os.path.join(output_dir, f"stories_{username}"))
        else:
            download_path = ensure_dir(
                os.path.join(self.output_dir, username, "stories")
            )

        downloaded_files = []
        story_metadata = []

        for i, story in enumerate(tqdm(stories, desc="Downloading stories")):
            try:
                # Determine media type and URL
                is_video = story.get("media_type") == 2

                if is_video:
                    video_versions = story.get("video_versions", [])
                    media_url = video_versions[0]["url"] if video_versions else ""
                    ext = ".mp4"
                else:
                    image_versions = story.get("image_versions2", {}).get("candidates", [])
                    media_url = image_versions[0]["url"] if image_versions else ""
                    ext = ".jpg"

                if not media_url:
                    continue

                filename = f"story_{i + 1:03d}{ext}"
                filepath = os.path.join(download_path, filename)

                self._download_file(media_url, filepath)
                downloaded_files.append(filepath)

                story_info = {
                    "index": i + 1,
                    "is_video": is_video,
                    "taken_at": story.get("taken_at", 0),
                    "filename": filename,
                }
                story_metadata.append(story_info)

            except Exception as e:
                logger.warning(f"Failed to download story {i + 1}: {e}")

        # Save metadata
        if story_metadata:
            metadata = {
                "username": username,
                "user_id": user_id,
                "total_stories": len(story_metadata),
                "stories": story_metadata,
            }
            metadata_path = os.path.join(download_path, "metadata.json")
            export_json(metadata, metadata_path)

        print_success(f"Downloaded {len(downloaded_files)} stories → {download_path}")
        return download_path

    def bulk_download(
        self,
        urls: List[str],
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """Download multiple posts from a list of URLs.

        Args:
            urls: List of Instagram post URLs or shortcodes.
            output_dir: Custom output directory.

        Returns:
            List of paths to downloaded directories.
        """
        print_header(f"Bulk downloading {len(urls)} posts")

        paths = []
        failed = []

        for i, url in enumerate(urls, 1):
            url = url.strip()
            if not url or url.startswith("#"):
                continue

            print_info(f"[{i}/{len(urls)}] Processing: {url}")

            try:
                path = self.download_post(url, output_dir)
                paths.append(path)
            except Exception as e:
                print_error(f"Failed: {e}")
                failed.append(url)

        # Summary
        print_header("Bulk Download Summary")
        print_success(f"Successfully downloaded: {len(paths)}")
        if failed:
            print_error(f"Failed: {len(failed)}")
            for f in failed:
                print_error(f"  → {f}")

        return paths

    def bulk_download_from_file(
        self,
        filepath: str,
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """Read URLs from a file and bulk download them.

        Args:
            filepath: Path to a text file with one URL per line.
            output_dir: Custom output directory.

        Returns:
            List of paths to downloaded directories.
        """
        if not os.path.exists(filepath):
            print_error(f"File not found: {filepath}")
            return []

        with open(filepath, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

        print_info(f"Loaded {len(urls)} URLs from {filepath}")
        return self.bulk_download(urls, output_dir)
