"""
Xiaohongshu (小红书) video extractor.

Parses the page HTML for embedded video data from __INITIAL_STATE__ or meta tags.
"""

import json
import logging
import re
from typing import Any, Dict

import httpx

logger = logging.getLogger("video-catch")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def extract_xiaohongshu(url: str) -> Dict[str, Any]:
    """
    Extract video from Xiaohongshu (小红书).

    Strategy:
    1. Follow redirects to get the actual page URL
    2. Parse __INITIAL_STATE__ for structured video data
    3. Fallback to meta tags and regex patterns
    """
    logger.info(f"Extracting Xiaohongshu video: {url}")

    async with httpx.AsyncClient(
        headers=HEADERS, follow_redirects=True, timeout=30.0
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    video_url = None
    title = "小红书视频"
    thumbnail = None
    author = None

    # Extract from meta tags
    og_video = re.search(r'<meta[^>]+(?:property|name)="og:video"[^>]+content="([^"]+)"', html)
    if og_video:
        video_url = og_video.group(1)

    og_title = re.search(r'<meta[^>]+(?:property="og:title"|name="og:title")[^>]+content="([^"]+)"', html)
    if og_title:
        title = og_title.group(1)

    og_image = re.search(r'<meta[^>]+(?:property|name)="og:image"[^>]+content="([^"]+)"', html)
    if og_image:
        raw_thumb = og_image.group(1)
        if raw_thumb.startswith("//"):
            raw_thumb = "https:" + raw_thumb
        thumbnail = raw_thumb

    # Try __INITIAL_STATE__ JSON
    initial_state = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*</script>', html, re.DOTALL)
    if initial_state:
        try:
            state_text = initial_state.group(1)
            state_text = re.sub(r'\bundefined\b', 'null', state_text)
            state = json.loads(state_text)

            note_detail = state.get("note", {}).get("noteDetailMap", {})
            for note_id, note_data in note_detail.items():
                note = note_data.get("note", {})
                if note.get("title"):
                    title = note["title"]
                if note.get("user", {}).get("nickname"):
                    author = note["user"]["nickname"]

                video_info = note.get("video", {})
                media = video_info.get("media", {})
                stream = media.get("stream", {})

                for quality_key in ["h265", "h264", "av1"]:
                    streams = stream.get(quality_key, [])
                    for s in streams:
                        master_url = s.get("masterUrl")
                        if master_url:
                            video_url = master_url
                            break
                    if video_url:
                        break

                if note.get("imageList"):
                    first_img = note["imageList"][0]
                    img_url = first_img.get("urlDefault") or first_img.get("url")
                    if img_url:
                        if img_url.startswith("//"):
                            img_url = "https:" + img_url
                        thumbnail = img_url
                break
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse __INITIAL_STATE__: {e}")

    if not video_url:
        video_src = re.search(r'(https?://[^"\']+\.mp4[^"\']*)', html)
        if video_src:
            video_url = video_src.group(1)

    if not video_url:
        raise ValueError("Could not find video in this Xiaohongshu post. It might be an image post.")

    formats = [
        {
            "quality": "原画",
            "url": video_url,
            "format": "mp4",
        }
    ]

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": None,
        "author": author,
        "formats": formats,
    }
