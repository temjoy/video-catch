"""
video-catch parsers — multi-platform video URL extraction.

Supported platforms:
  - Bilibili (bilibili.com, b23.tv)
  - Douyin (douyin.com, v.douyin.com)
  - Xiaohongshu (xiaohongshu.com, xhslink.com)
  - Pinterest (pinterest.com, pin.it)
  - Vimeo (vimeo.com)
  - Twitter/X (twitter.com, x.com) — requires yt-dlp

Each parser exposes an async `extract_<platform>(url)` function that returns
a standardized dict:
    {
        "title": str,
        "thumbnail": str | None,
        "duration": str | None,   # "M:SS" or "H:MM:SS"
        "author": str | None,
        "platform": str,
        "formats": [
            {
                "quality": str,        # e.g. "1080p", "720p", "原画"
                "resolution": str?,    # e.g. "1920x1080"
                "fileSize": str?,      # e.g. "12.3 MB"
                "url": str,            # direct download URL
                "format": str,         # file extension: "mp4", "jpg"
            }
        ]
    }
"""

from .dispatcher import extract, detect_platform

__all__ = ["extract", "detect_platform"]
