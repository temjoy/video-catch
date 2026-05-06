"""
Twitter/X video extractor.

Uses yt-dlp as the extraction engine.
Requires: pip install yt-dlp
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("video-catch")

try:
    import yt_dlp
    HAS_YT_DLP = True
except ImportError:
    HAS_YT_DLP = False

YDL_OPTS: Dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,
    "socket_timeout": 30,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
}

# Support optional cookies file
COOKIES_FILE = os.environ.get("TWITTER_COOKIES_FILE", "")
if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
    YDL_OPTS["cookiefile"] = COOKIES_FILE


def _format_filesize(size_bytes: Optional[int]) -> Optional[str]:
    if size_bytes is None:
        return None
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _extract_sync(url: str) -> Dict[str, Any]:
    if not HAS_YT_DLP:
        raise ImportError(
            "yt-dlp is required for Twitter extraction. "
            "Install with: pip install yt-dlp"
        )

    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not extract video info from Twitter")

    formats = []
    seen_qualities = set()

    for f in sorted(
        info.get("formats", []),
        key=lambda x: (x.get("height") or 0),
        reverse=True,
    ):
        height = f.get("height")
        if not height or not f.get("url"):
            continue
        quality_label = f"{height}p"
        if quality_label in seen_qualities:
            continue
        seen_qualities.add(quality_label)
        formats.append({
            "quality": quality_label,
            "resolution": f"{f.get('width', '?')}x{height}",
            "fileSize": _format_filesize(f.get("filesize") or f.get("filesize_approx")),
            "url": f["url"],
            "format": f.get("ext", "mp4"),
        })
        if len(formats) >= 5:
            break

    return {
        "title": info.get("title") or info.get("description", "Twitter Video")[:80],
        "thumbnail": info.get("thumbnail"),
        "duration": None,
        "author": info.get("uploader") or info.get("uploader_id"),
        "formats": formats[:5],
    }


async def extract_twitter(url: str) -> Dict[str, Any]:
    """Extract video from Twitter/X. Requires yt-dlp."""
    logger.info(f"Extracting Twitter video: {url}")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_sync, url)
