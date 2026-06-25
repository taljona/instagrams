"""
insta-tools — A powerful Instagram scraping toolkit.

Scrape profiles, download posts & stories, analyze hashtags — no API key needed.
"""

__version__ = "1.0.0"
__author__ = "taljona"

from instatools.scraper import Scraper
from instatools.downloader import Downloader
from instatools.analyzer import Analyzer
from instatools.utils import setup_logging

__all__ = ["Scraper", "Downloader", "Analyzer", "setup_logging"]
