"""
Shared utilities for insta-tools.

Provides session management, retry logic, output formatting, and common helpers.
"""

import os
import sys
import json
import time
import logging
import functools
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from colorama import Fore, Style, init as colorama_init

# Initialize colorama for cross-platform colored output
colorama_init()

logger = logging.getLogger("instatools")

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
}

DEFAULT_DOWNLOAD_DIR = "./downloads"
DEFAULT_DELAY = 2  # seconds between requests
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff multiplier


# ─── Logging Setup ────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO, quiet: bool = False) -> logging.Logger:
    """Configure logging for insta-tools."""
    if quiet:
        level = logging.WARNING

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            f"{Fore.CYAN}%(asctime)s{Style.RESET_ALL} "
            f"{Fore.YELLOW}[%(levelname)s]{Style.RESET_ALL} %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


# ─── Session Management ───────────────────────────────────────────────────────

def create_session(cookie: Optional[str] = None) -> requests.Session:
    """Create a requests session with Instagram-compatible headers.

    Args:
        cookie: Optional cookie string for authenticated requests.

    Returns:
        Configured requests.Session object.
    """
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    if cookie:
        session.headers["Cookie"] = cookie

    return session


# ─── Retry Decorator ──────────────────────────────────────────────────────────

def retry(
    max_retries: int = MAX_RETRIES,
    backoff: float = RETRY_BACKOFF,
    delay: float = DEFAULT_DELAY,
    exceptions: tuple = (requests.RequestException, ConnectionError, TimeoutError),
):
    """Decorator that retries a function on failure with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        backoff: Multiplier for delay between retries.
        delay: Initial delay in seconds.
        exceptions: Tuple of exception types to catch.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    status_code = getattr(e, "response", None)
                    status_code = getattr(status_code, "status_code", None)

                    if status_code == 429:
                        # Rate limited — use longer delay
                        current_delay = max(current_delay * backoff * 2, 30)
                        logger.warning(
                            f"{Fore.YELLOW}Rate limited. Waiting {current_delay:.0f}s "
                            f"(attempt {attempt}/{max_retries}){Style.RESET_ALL}"
                        )
                    elif status_code in (401, 403):
                        logger.error(
                            f"{Fore.RED}Authentication/authorization error "
                            f"(HTTP {status_code}). Skipping.{Style.RESET_ALL}"
                        )
                        raise
                    elif status_code == 404:
                        logger.error(
                            f"{Fore.RED}Resource not found (HTTP 404). Skipping.{Style.RESET_ALL}"
                        )
                        raise
                    else:
                        logger.warning(
                            f"{Fore.YELLOW}Request failed: {e}. "
                            f"Retrying in {current_delay:.0f}s "
                            f"(attempt {attempt}/{max_retries}){Style.RESET_ALL}"
                        )

                    time.sleep(current_delay)
                    current_delay *= backoff

            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# ─── Output Formatting ────────────────────────────────────────────────────────

def print_header(text: str) -> None:
    """Print a styled section header."""
    width = 60
    print()
    print(f"{Fore.CYAN}{'═' * width}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}  {text}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═' * width}{Style.RESET_ALL}")


def print_field(label: str, value: Any, indent: int = 2) -> None:
    """Print a labeled field with color formatting."""
    spaces = " " * indent
    print(f"{spaces}{Fore.GREEN}{label}:{Style.RESET_ALL} {value}")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print(f"{Fore.YELLOW}⚠ {text}{Style.RESET_ALL}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(f"{Fore.BLUE}ℹ {text}{Style.RESET_ALL}")


def format_number(n: int) -> str:
    """Format a number with K/M/B suffixes for readability.

    Args:
        n: Integer to format.

    Returns:
        Formatted string like '1.2M' or '15.3K'.
    """
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    elif n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# ─── File & Export Helpers ────────────────────────────────────────────────────

def ensure_dir(path: str) -> str:
    """Create directory if it doesn't exist and return the path."""
    os.makedirs(path, exist_ok=True)
    return path


def export_json(data: Any, filepath: str) -> str:
    """Export data to a JSON file.

    Args:
        data: Serializable data object.
        filepath: Path to the output file.

    Returns:
        The filepath that was written.
    """
    ensure_dir(os.path.dirname(filepath) or ".")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"Exported JSON to {filepath}")
    return filepath


def generate_json_path(base_name: str, output_dir: str = ".") -> str:
    """Generate a timestamped JSON file path.

    Args:
        base_name: Base name for the file (e.g., 'profile_natgeo').
        output_dir: Directory to save in.

    Returns:
        Full file path like './output/profile_natgeo_20240101_120000.json'.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{timestamp}.json"
    return os.path.join(output_dir, filename)


# ─── URL Parsing ──────────────────────────────────────────────────────────────

def extract_shortcode(url: str) -> Optional[str]:
    """Extract the shortcode from an Instagram post URL.

    Args:
        url: Instagram post URL (e.g., 'https://www.instagram.com/p/CxYzAbCdEfG/').

    Returns:
        The shortcode or None if not found.
    """
    import re

    patterns = [
        r"instagram\.com/p/([A-Za-z0-9_-]+)",
        r"instagram\.com/reel/([A-Za-z0-9_-]+)",
        r"instagram\.com/tv/([A-Za-z0-9_-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def normalize_username(username: str) -> str:
    """Strip @ symbol and whitespace from a username.

    Args:
        username: Raw username string.

    Returns:
        Clean username without @ prefix.
    """
    return username.strip().lstrip("@").strip("/")


def get_download_path(
    username: str = "unknown",
    output_dir: str = DEFAULT_DOWNLOAD_DIR,
) -> str:
    """Generate a download directory path for a user's content.

    Args:
        username: Instagram username.
        output_dir: Base download directory.

    Returns:
        Path like './downloads/username/'.
    """
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in username)
    return ensure_dir(os.path.join(output_dir, safe_name))
