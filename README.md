# 📸 insta-tools — Instagram Toolkit

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/github/stars/taljona/instagrams?style=for-the-badge&logo=github" alt="Stars">
  <img src="https://img.shields.io/github/forks/taljona/instagrams?style=for-the-badge&logo=github" alt="Forks">
  <img src="https://img.shields.io/badge/version-1.0.0-purple?style=for-the-badge" alt="Version">
</p>

<p align="center">
  <b>A powerful, no-API-key-needed Instagram scraping toolkit.</b><br>
  Scrape profiles, download posts & stories, analyze hashtags — all from the CLI.
</p>

---

## ✨ Features

- 🔍 **Profile Scraper** — Extract any public Instagram profile data (bio, followers, following, post count, profile pic, verified status)
- ⬇️ **Post Downloader** — Download images and videos from Instagram post URLs with full metadata
- 📖 **Story Viewer** — View and download stories from public profiles
- 📊 **Hashtag Analyzer** — Analyze hashtag usage, top posts, related hashtags, and engagement metrics
- 📦 **Bulk Operations** — Download all posts from a profile or batch-download from a URL list
- 💾 **JSON Export** — Export any scrape result to JSON for further processing
- 🎨 **Colorful CLI** — Beautiful terminal output with progress bars
- 🛡️ **Rate Limit Handling** — Automatic retries with exponential backoff
- 🔑 **No API Key Required** — Works with Instagram's public web endpoints

## 📦 Installation

```bash
# Install from source
git clone https://github.com/taljona/instagrams.git
cd instagrams
pip install -e .

# Or install directly
pip install insta-tools
```

### Requirements

- Python 3.8+
- `requests`
- `beautifulsoup4`
- `tqdm`
- `colorama`

## 🚀 Quick Start

### As a CLI tool

```bash
# Scrape a profile
instatools profile instagram

# Download a post
instatools download "https://www.instagram.com/p/CxYzAbCdEfG/"

# View stories
instatools stories natgeo

# Analyze a hashtag
instatools hashtag travel

# Bulk download from a file of URLs
instatools bulk urls.txt
```

### As a Python library

```python
from instatools import Scraper, Downloader, Analyzer

# Scrape a profile
scraper = Scraper()
profile = scraper.get_profile("natgeo")
print(f"{profile['full_name']} — {profile['follower_count']:,} followers")

# Download a post
dl = Downloader()
dl.download_post("https://www.instagram.com/p/CxYzAbCdEfG/")

# Analyze a hashtag
analyzer = Analyzer()
stats = analyzer.analyze_hashtag("travel")
print(f"Top post likes: {stats['top_post']['likes']}")
```

## 📖 CLI Reference

| Command | Description | Example |
|---------|-------------|---------|
| `instatools profile <username>` | Scrape profile info | `instatools profile natgeo` |
| `instatools download <url>` | Download post media | `instatools download "https://instagram.com/p/ABC123/"` |
| `instatools stories <username>` | View/download stories | `instatools stories natgeo` |
| `instatools hashtag <tag>` | Analyze hashtag | `instatools hashtag travel` |
| `instatools bulk <file>` | Batch download URLs | `instatools bulk urls.txt` |

### Global Options

| Flag | Description |
|------|-------------|
| `--json` | Export results to JSON file |
| `--output-dir DIR` | Custom download directory (default: `./downloads`) |
| `--delay SECONDS` | Delay between requests (default: `2`) |
| `--quiet` | Suppress colored output |

## 📁 Project Structure

```
instagrams/
├── README.md
├── LICENSE
├── requirements.txt
├── setup.py
├── .gitignore
├── instatools/
│   ├── __init__.py
│   ├── cli.py          # CLI entry point
│   ├── scraper.py      # Profile scraper
│   ├── downloader.py   # Post/story downloader
│   ├── analyzer.py     # Hashtag analytics
│   └── utils.py        # Shared utilities
└── examples/
    └── basic_usage.py
```

## ⚠️ Disclaimer

This tool is for **educational and research purposes only**. Scraping Instagram may violate their Terms of Service. Use responsibly and respect rate limits. The authors are not responsible for any misuse of this software.

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  If you find this useful, please ⭐ star the repo — it helps others discover it!
</p>
