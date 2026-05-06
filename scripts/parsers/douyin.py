"""
Douyin (抖音) video extractor.

Strategy (multi-tier fallback):
    1. Primary: Fetch SSR-rendered mobile share page from iesdouyin.com,
       parse `_ROUTER_DATA` for video metadata + play URLs.
    2. Fallback: Call Douyin web API with auto-generated cookies.

Requirements:
    - Works best from a mainland China IP.
    - Set `DOUYIN_PROXY` env var (e.g. `socks5://user:pass@host:port`)
      to route requests through a CN proxy when running overseas.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("video-catch")

DOUYIN_PROXY = os.environ.get("DOUYIN_PROXY", "")

_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)

_DESKTOP_HEADERS = {
    "User-Agent": _DESKTOP_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.douyin.com/",
}

_MOBILE_HEADERS = {
    "User-Agent": _MOBILE_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _format_duration(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    total_secs = ms // 1000
    mins, secs = divmod(total_secs, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _format_filesize(size_bytes: Optional[int]) -> Optional[str]:
    if size_bytes is None:
        return None
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _extract_video_id(url: str) -> Optional[str]:
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"modal_id=(\d+)", url)
    if m:
        return m.group(1)
    return None


def _pick_best_url(url_list: List[str]) -> Optional[str]:
    if not url_list:
        return None
    for u in url_list:
        if "play" in u and "playwm" not in u:
            return u
    best = url_list[0]
    if "playwm" in best:
        best = best.replace("playwm", "play")
    return best


def _quality_label(width: int, height: int) -> str:
    short = max(width, height)
    if short >= 2160:
        return "4K"
    if short >= 1440:
        return "2K"
    if short >= 1080:
        return "1080p"
    if short >= 720:
        return "720p"
    if short >= 480:
        return "480p"
    if short >= 360:
        return "360p"
    return f"{height}p"


def _get_proxy_kwargs() -> dict:
    if DOUYIN_PROXY:
        return {"proxy": DOUYIN_PROXY}
    return {}


async def _get_ttwid() -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0, **_get_proxy_kwargs()) as client:
            resp = await client.post(
                "https://ttwid.bytedance.com/ttwid/union/register/",
                json={
                    "region": "cn",
                    "aid": 6383,
                    "needFid": False,
                    "service": "www.douyin.com",
                    "migrate_info": {"ticket": "", "source": "node"},
                    "cbUrlProtocol": "https",
                    "union": True,
                },
                headers={"Content-Type": "application/json"},
            )
            return resp.cookies.get("ttwid", "")
    except Exception as e:
        logger.warning(f"Failed to get ttwid: {e}")
        return ""


async def _resolve_short_link(url: str) -> str:
    if "douyin.com/video/" in url:
        return url
    try:
        async with httpx.AsyncClient(
            headers=_MOBILE_HEADERS,
            follow_redirects=True,
            timeout=15.0,
            **_get_proxy_kwargs(),
        ) as client:
            resp = await client.get(url)
            return str(resp.url)
    except Exception as e:
        logger.warning(f"Failed to resolve short link: {e}")
        return url


def _parse_item(item: dict) -> Dict[str, Any]:
    video = item.get("video", {})
    author_info = item.get("author", {})

    title = item.get("desc", "").strip() or "抖音视频"
    author_name = author_info.get("nickname", "")

    cover = video.get("cover", {})
    cover_urls = cover.get("url_list", [])
    dynamic_cover = video.get("dynamic_cover", {}).get("url_list", [])
    thumbnail = (cover_urls[0] if cover_urls else
                 dynamic_cover[0] if dynamic_cover else None)

    duration_ms = video.get("duration", 0)
    duration = _format_duration(duration_ms)

    formats = []
    seen_qualities = set()

    bit_rate_list = video.get("bit_rate") or []
    for br in sorted(bit_rate_list,
                     key=lambda x: x.get("play_addr", {}).get("height", 0),
                     reverse=True):
        play_addr = br.get("play_addr", {})
        urls = play_addr.get("url_list", [])
        best_url = _pick_best_url(urls)
        if not best_url:
            continue

        w = play_addr.get("width", 0)
        h = play_addr.get("height", 0)
        label = _quality_label(w, h)

        if label in seen_qualities:
            continue
        seen_qualities.add(label)

        formats.append({
            "quality": label,
            "resolution": f"{w}x{h}" if w and h else None,
            "fileSize": _format_filesize(play_addr.get("data_size")),
            "url": best_url,
            "format": "mp4",
        })
        if len(formats) >= 5:
            break

    if not formats:
        play_addr = video.get("play_addr", {})
        urls = play_addr.get("url_list", [])
        best_url = _pick_best_url(urls)
        if best_url:
            w = play_addr.get("width", video.get("width", 0))
            h = play_addr.get("height", video.get("height", 0))
            formats.append({
                "quality": _quality_label(w, h) if w and h else "原画",
                "resolution": f"{w}x{h}" if w and h else None,
                "fileSize": _format_filesize(play_addr.get("data_size")),
                "url": best_url,
                "format": "mp4",
            })

    dl_addr = video.get("download_addr", {})
    dl_urls = dl_addr.get("url_list", [])
    if dl_urls and not any(f["quality"] == "原画" for f in formats):
        formats.insert(0, {
            "quality": "原画",
            "resolution": None,
            "fileSize": _format_filesize(dl_addr.get("data_size")),
            "url": dl_urls[0],
            "format": "mp4",
        })

    if not formats:
        raise ValueError("No video found in this Douyin post")

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": duration,
        "author": author_name,
        "formats": formats[:5],
    }


async def _extract_via_ssr(video_id: str) -> Optional[Dict[str, Any]]:
    url = f"https://www.iesdouyin.com/share/video/{video_id}/"

    try:
        ttwid = await _get_ttwid()
        cookies = {"ttwid": ttwid} if ttwid else {}

        async with httpx.AsyncClient(
            headers=_MOBILE_HEADERS,
            follow_redirects=True,
            timeout=30.0,
            cookies=cookies,
            **_get_proxy_kwargs(),
        ) as client:
            resp = await client.get(url)
            html = resp.text

        router_match = re.search(
            r"window\._ROUTER_DATA\s*=\s*(\{.+?\})\s*</script>",
            html, re.DOTALL,
        )
        if not router_match:
            return None

        raw = router_match.group(1)
        try:
            data = json.loads(raw, strict=False)
        except json.JSONDecodeError:
            try:
                decoded = raw.encode("utf-8").decode("unicode_escape")
                data = json.loads(decoded, strict=False)
            except (UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError):
                cleaned = raw.replace("\\u002F", "/")
                data = json.loads(cleaned, strict=False)

        loader = data.get("loaderData", {})
        for _key, val in loader.items():
            if not isinstance(val, dict):
                continue
            vir = val.get("videoInfoRes")
            if not vir:
                continue
            items = vir.get("item_list", [])
            if not items:
                return None
            return _parse_item(items[0])

        return None
    except Exception as e:
        logger.warning(f"SSR extraction failed: {e}")
        return None


async def _extract_via_web_api(video_id: str) -> Optional[Dict[str, Any]]:
    try:
        ttwid = await _get_ttwid()
        cookies = {"ttwid": ttwid} if ttwid else {}

        async with httpx.AsyncClient(
            headers={
                **_DESKTOP_HEADERS,
                "Accept": "application/json",
                "Referer": f"https://www.douyin.com/video/{video_id}",
            },
            follow_redirects=True,
            timeout=30.0,
            cookies=cookies,
            **_get_proxy_kwargs(),
        ) as client:
            resp = await client.get(
                "https://www.douyin.com/aweme/v1/web/aweme/detail/",
                params={
                    "aweme_id": video_id,
                    "device_platform": "webapp",
                    "aid": "6383",
                },
            )

            if not resp.text.strip():
                return None

            data = resp.json()
            detail = data.get("aweme_detail")
            if not detail:
                return None

            return _parse_item(detail)
    except Exception as e:
        logger.warning(f"Web API extraction failed: {e}")
        return None


async def extract_douyin(url: str) -> Dict[str, Any]:
    """
    Extract video info from a Douyin URL.

    Requires mainland China IP or DOUYIN_PROXY environment variable.
    """
    logger.info(f"Extracting Douyin video: {url}")

    resolved_url = await _resolve_short_link(url)
    video_id = _extract_video_id(resolved_url)

    if not video_id:
        raise ValueError("Could not extract Douyin video ID from URL")

    result = await _extract_via_ssr(video_id)
    if result:
        return result

    result = await _extract_via_web_api(video_id)
    if result:
        return result

    raise ValueError(
        "Cannot extract Douyin video. This requires a mainland China IP. "
        "Set DOUYIN_PROXY env var if running overseas."
    )
