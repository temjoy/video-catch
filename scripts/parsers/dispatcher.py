"""
URL dispatcher — detects platform from URL and routes to the correct parser.
"""

import re
import logging
from typing import Any, Dict

logger = logging.getLogger("video-catch")

PLATFORM_PATTERNS = {
    "twitter": [
        re.compile(r"(?:https?://)?(?:www\.)?twitter\.com/.+/status/", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?x\.com/.+/status/", re.IGNORECASE),
        re.compile(r"(?:https?://)?t\.co/", re.IGNORECASE),
    ],
    "xiaohongshu": [
        re.compile(r"(?:https?://)?(?:www\.)?xiaohongshu\.com/", re.IGNORECASE),
        re.compile(r"(?:https?://)?xhslink\.com/", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?xhs\.cn/", re.IGNORECASE),
    ],
    "pinterest": [
        re.compile(r"(?:https?://)?(?:www\.)?pinterest\.com/pin/", re.IGNORECASE),
        re.compile(r"(?:https?://)?pin\.it/", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?pinterest\.[a-z.]+/pin/", re.IGNORECASE),
    ],
    "bilibili": [
        re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:m\.)?bilibili\.com/video/", re.IGNORECASE),
        re.compile(r"(?:https?://)?b23\.tv/", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/bangumi/", re.IGNORECASE),
    ],
    "vimeo": [
        re.compile(r"(?:https?://)?(?:www\.)?vimeo\.com/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?player\.vimeo\.com/video/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?vimeo\.com/channels/.+/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?vimeo\.com/groups/.+/videos/\d+", re.IGNORECASE),
    ],
    "douyin": [
        re.compile(r"(?:https?://)?(?:www\.)?douyin\.com/video/\d+", re.IGNORECASE),
        re.compile(r"(?:https?://)?v\.douyin\.com/", re.IGNORECASE),
        re.compile(r"(?:https?://)?(?:www\.)?iesdouyin\.com/share/video/\d+", re.IGNORECASE),
    ],
}


def detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to. Returns platform name or 'unknown'."""
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(url):
                return platform
    return "unknown"


async def extract(url: str) -> Dict[str, Any]:
    """
    Extract video info from a URL. Auto-detects platform.

    Returns standardized dict with title, thumbnail, duration, author, platform, formats.
    Raises ValueError if platform is unsupported or extraction fails.
    """
    platform = detect_platform(url)
    logger.info(f"Detected platform: {platform} for URL: {url}")

    if platform == "unknown":
        raise ValueError(
            f"Unsupported platform. Supported: "
            f"{', '.join(PLATFORM_PATTERNS.keys())}"
        )

    # Lazy imports to avoid loading all parsers unnecessarily
    if platform == "bilibili":
        from .bilibili import extract_bilibili
        result = await extract_bilibili(url)
    elif platform == "douyin":
        from .douyin import extract_douyin
        result = await extract_douyin(url)
    elif platform == "xiaohongshu":
        from .xiaohongshu import extract_xiaohongshu
        result = await extract_xiaohongshu(url)
    elif platform == "pinterest":
        from .pinterest import extract_pinterest
        result = await extract_pinterest(url)
    elif platform == "vimeo":
        from .vimeo import extract_vimeo
        result = await extract_vimeo(url)
    elif platform == "twitter":
        from .twitter import extract_twitter
        result = await extract_twitter(url)
    else:
        raise ValueError(f"No extractor for platform: {platform}")

    result["platform"] = platform
    return result
