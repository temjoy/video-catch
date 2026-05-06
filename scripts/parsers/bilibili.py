"""
Bilibili video extractor.

Extracts video info and download URLs from Bilibili using official API.
Supports BV/AV IDs, short links (b23.tv), multi-page videos, and DASH format.

Note: Bilibili video URLs have anti-hotlink protection (Referer check).
      When downloading, you must set `Referer: https://www.bilibili.com/` header.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("video-catch")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

VIEW_API = "https://api.bilibili.com/x/web-interface/view"
PLAY_URL_API = "https://api.bilibili.com/x/player/playurl"

QUALITY_MAP = {
    127: "8K", 126: "杜比视界", 125: "HDR", 120: "4K",
    116: "1080P60", 112: "1080P+", 80: "1080P", 74: "720P60",
    64: "720P", 32: "480P", 16: "360P",
}


def _extract_bvid(url: str) -> Optional[str]:
    match = re.search(r"(BV[a-zA-Z0-9]{10})", url)
    return match.group(1) if match else None


def _extract_avid(url: str) -> Optional[str]:
    match = re.search(r"av(\d+)", url, re.IGNORECASE)
    return match.group(1) if match else None


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"


async def _resolve_short_url(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.head(url, follow_redirects=True)
    return str(resp.url)


async def _get_video_info(client: httpx.AsyncClient, bvid=None, avid=None) -> Dict:
    params = {}
    if bvid:
        params["bvid"] = bvid
    elif avid:
        params["aid"] = avid
    else:
        raise ValueError("Either bvid or avid is required")

    resp = await client.get(VIEW_API, params=params)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        msg = data.get("message", "Unknown error")
        raise ValueError(f"Bilibili API error: {msg}")

    return data["data"]


async def _get_play_url(client: httpx.AsyncClient, bvid: str, cid: int, use_dash=False) -> Dict:
    params = {
        "bvid": bvid,
        "cid": cid,
        "qn": 120,
        "fnval": 16 if use_dash else 0,
        "fourk": 1,
    }
    resp = await client.get(PLAY_URL_API, params=params)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"Play URL error: {data.get('message', 'Unknown')}")
    return data["data"]


def _build_formats_from_durl(play_data: Dict) -> List[Dict[str, Any]]:
    formats = []
    quality = play_data.get("quality", 0)
    quality_label = QUALITY_MAP.get(quality, f"{quality}")
    durl_list = play_data.get("durl", [])

    for entry in durl_list:
        url = entry.get("url", "")
        size = entry.get("size", 0)
        if not url:
            continue
        fmt = {
            "quality": quality_label,
            "url": url,
            "format": "mp4",
        }
        if size > 0:
            fmt["fileSize"] = _format_file_size(size)
        formats.append(fmt)

    return formats


def _build_formats_from_dash(play_data: Dict) -> List[Dict[str, Any]]:
    formats = []
    dash = play_data.get("dash")
    if not dash:
        return formats

    video_tracks = dash.get("video", [])
    seen_qualities = {}

    for track in video_tracks:
        qid = track.get("id", 0)
        url = track.get("baseUrl") or track.get("base_url", "")
        if not url:
            continue

        codecs = track.get("codecs", "")
        is_avc = "avc" in codecs.lower()

        if qid in seen_qualities:
            if is_avc and not seen_qualities[qid].get("_is_avc"):
                pass
            else:
                continue

        width = track.get("width", 0)
        height = track.get("height", 0)
        quality_label = QUALITY_MAP.get(qid, f"{qid}")

        seen_qualities[qid] = {
            "quality": quality_label,
            "resolution": f"{width}x{height}" if width and height else None,
            "url": url,
            "format": "mp4",
            "videoOnly": True,
            "_is_avc": is_avc,
        }

    for qid in sorted(seen_qualities.keys(), reverse=True):
        entry = seen_qualities[qid]
        entry.pop("_is_avc", None)
        formats.append(entry)

    return formats


async def extract_bilibili(url: str) -> Dict[str, Any]:
    """
    Extract video info and download links from Bilibili.

    Returns standardized result dict.
    Note: Download URLs require `Referer: https://www.bilibili.com/` header.
    """
    logger.info(f"Extracting Bilibili video: {url}")

    async with httpx.AsyncClient(
        headers=HEADERS.copy(), follow_redirects=True, timeout=30.0
    ) as client:

        if "b23.tv" in url:
            url = await _resolve_short_url(client, url)

        bvid = _extract_bvid(url)
        avid = _extract_avid(url) if not bvid else None

        if not bvid and not avid:
            raise ValueError("Cannot extract Bilibili video ID from URL")

        video_info = await _get_video_info(client, bvid=bvid, avid=avid)

        title = video_info.get("title", "Bilibili Video")
        raw_thumbnail = video_info.get("pic", "")
        if raw_thumbnail and raw_thumbnail.startswith("http://"):
            raw_thumbnail = "https://" + raw_thumbnail[7:]
        thumbnail = raw_thumbnail or None

        duration_sec = video_info.get("duration", 0)
        duration = _format_duration(duration_sec) if duration_sec > 0 else None

        owner = video_info.get("owner", {})
        author = owner.get("name")

        bvid = bvid or video_info.get("bvid", "")
        cid = video_info.get("cid")

        # Handle multi-page videos
        page_num = 1
        page_match = re.search(r"[?&]p=(\d+)", url)
        if page_match:
            page_num = int(page_match.group(1))

        pages = video_info.get("pages", [])
        if pages and page_num <= len(pages):
            page_info = pages[page_num - 1]
            cid = page_info.get("cid", cid)
            if len(pages) > 1:
                page_title = page_info.get("part", "")
                if page_title:
                    title = f"{title} - {page_title}"

        if not cid:
            raise ValueError("Cannot get video cid")

        # Get download URLs
        formats = []

        try:
            durl_data = await _get_play_url(client, bvid, cid, use_dash=False)
            formats = _build_formats_from_durl(durl_data)
        except Exception as e:
            logger.warning(f"durl mode failed: {e}")

        try:
            dash_data = await _get_play_url(client, bvid, cid, use_dash=True)
            dash_formats = _build_formats_from_dash(dash_data)
            existing_qualities = {f["quality"] for f in formats}
            for df in dash_formats:
                if df["quality"] not in existing_qualities:
                    formats.append(df)
        except Exception as e:
            logger.warning(f"DASH mode failed: {e}")

        if not formats:
            raise ValueError("Cannot get video download URLs")

        return {
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "author": author,
            "formats": formats,
        }
