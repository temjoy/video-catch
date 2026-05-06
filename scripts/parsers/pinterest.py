"""
Pinterest video/image extractor.

Uses Pinterest's internal PinResource API.
Supports pin.it short links (with DNS-over-HTTPS fallback), HLS parsing,
Story/Idea pins, and regular video pins.

Note: Pinterest CDN (.pinimg.com) requires `Referer: https://www.pinterest.com/` header.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("video-catch")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*, q=0.01",
    "Referer": "https://www.pinterest.com/",
    "X-Requested-With": "XMLHttpRequest",
    "X-Pinterest-PWS-Handler": "www/pin.js",
    "X-APP-VERSION": "0",
}

PIN_API_URL = "https://www.pinterest.com/resource/PinResource/get/"


def _extract_pin_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in ("pin.it",):
        return ""
    match = re.search(r"/pin/(?:[^/]*--)?(\d+)", url)
    return match.group(1) if match else ""


async def _resolve_short_url(url: str) -> str:
    """Resolve pin.it short links."""
    parsed = urlparse(url)
    short_code = parsed.path.strip("/")

    # Strategy 1: Pinterest's URL shortener API
    if short_code:
        try:
            api_url = f"https://api.pinterest.com/url_shortener/{short_code}/redirect/"
            async with httpx.AsyncClient(
                headers={"User-Agent": HEADERS["User-Agent"]},
                follow_redirects=True,
                timeout=15.0,
            ) as api_client:
                resp = await api_client.get(api_url)
                final_url = str(resp.url)
                if "pinterest.com" in final_url and "/pin/" in final_url:
                    return final_url
                for redirect_resp in resp.history:
                    loc = str(redirect_resp.url)
                    if "/pin/" in loc:
                        return loc
        except Exception as e:
            logger.warning(f"Pinterest API shortener failed: {e}")

    # Strategy 2: Direct resolution
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": HEADERS["User-Agent"]},
            follow_redirects=True,
            timeout=10.0,
        ) as short_client:
            resp = await short_client.head(url)
            final_url = str(resp.url)
            if "pinterest.com" in final_url:
                return final_url
    except Exception as e:
        logger.warning(f"Direct pin.it resolution failed: {e}")

    # Strategy 3: DNS-over-HTTPS
    try:
        async with httpx.AsyncClient(timeout=10.0) as dns_client:
            pin_it_ip = await _resolve_dns_over_https(dns_client, "pin.it")
        if pin_it_ip:
            path = parsed.path or "/"
            ip_url = f"https://{pin_it_ip}{path}"
            async with httpx.AsyncClient(verify=False, timeout=10.0) as ip_client:
                resp = await ip_client.get(
                    ip_url,
                    headers={"User-Agent": HEADERS["User-Agent"], "Host": "pin.it"},
                    follow_redirects=True,
                )
                final = str(resp.url)
                if "pinterest.com" in final:
                    return final
    except Exception as e:
        logger.warning(f"DoH pin.it resolution failed: {e}")

    raise ValueError("Could not resolve Pinterest short link. Try using the full pinterest.com URL.")


async def _resolve_dns_over_https(client: httpx.AsyncClient, domain: str) -> Optional[str]:
    try:
        resp = await client.get(
            "https://cloudflare-dns.com/dns-query",
            params={"name": domain, "type": "A"},
            headers={"Accept": "application/dns-json"},
            timeout=5.0,
        )
        for ans in resp.json().get("Answer", []):
            if ans.get("type") == 1:
                return ans.get("data")
    except Exception:
        pass
    try:
        resp = await client.get(
            "https://dns.google/resolve",
            params={"name": domain, "type": "A"},
            timeout=5.0,
        )
        for ans in resp.json().get("Answer", []):
            if ans.get("type") == 1:
                return ans.get("data")
    except Exception:
        pass
    return None


async def _get_csrf_token(client: httpx.AsyncClient) -> str:
    for attempt in range(3):
        try:
            resp = await client.get("https://www.pinterest.com/", timeout=15.0)
            token = client.cookies.get("csrftoken", "")
            if token:
                return token
            for cookie_header in resp.headers.get_list("set-cookie"):
                if "csrftoken=" in cookie_header:
                    match = re.search(r"csrftoken=([^;]+)", cookie_header)
                    if match:
                        return match.group(1)
        except Exception as e:
            logger.warning(f"CSRF token attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                import asyncio
                await asyncio.sleep(1)
    return ""


async def _parse_hls_formats(hls_url: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Parse HLS master playlist and extract downloadable .cmfv video URLs."""
    base_url = hls_url.rsplit("/", 1)[0] + "/"
    formats = []

    try:
        resp = await client.get(hls_url, timeout=10.0)
        if resp.status_code != 200:
            return formats

        master_text = resp.text
        streams = []
        lines = master_text.strip().split("\n")
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF:"):
                res_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
                bw_match = re.search(r"BANDWIDTH=(\d+)", line)
                width = int(res_match.group(1)) if res_match else 0
                height = int(res_match.group(2)) if res_match else 0
                bandwidth = int(bw_match.group(1)) if bw_match else 0
                if i + 1 < len(lines):
                    sub_url = lines[i + 1].strip()
                    if not sub_url.startswith("http"):
                        sub_url = base_url + sub_url
                    streams.append({
                        "width": width, "height": height,
                        "bandwidth": bandwidth, "sub_url": sub_url,
                    })

        streams.sort(key=lambda s: s["height"], reverse=True)

        for stream in streams:
            try:
                sub_resp = await client.get(stream["sub_url"], timeout=10.0)
                if sub_resp.status_code != 200:
                    continue
                sub_text = sub_resp.text
                sub_base = stream["sub_url"].rsplit("/", 1)[0] + "/"

                map_match = re.search(r'EXT-X-MAP:URI="([^"]+)"', sub_text)
                if map_match:
                    media_file = map_match.group(1)
                    if not media_file.startswith("http"):
                        media_file = sub_base + media_file

                    head_resp = await client.head(media_file, timeout=5.0)
                    if head_resp.status_code == 200:
                        h = stream["height"]
                        quality_label = f"{h}p" if h else f"{stream['width']}w"
                        fmt = {
                            "quality": quality_label,
                            "resolution": f"{stream['width']}x{h}" if h else None,
                            "url": media_file,
                            "format": "mp4",
                        }
                        cl = head_resp.headers.get("content-length")
                        if cl:
                            size_mb = int(cl) / (1024 * 1024)
                            fmt["fileSize"] = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{int(cl) / 1024:.0f} KB"
                        formats.append(fmt)
            except Exception as e:
                logger.warning(f"Failed to parse sub-playlist: {e}")
                continue
    except Exception as e:
        logger.warning(f"Failed to parse HLS master playlist: {e}")

    return formats


async def _extract_formats_from_video_list(
    video_list: Dict[str, Any], client: httpx.AsyncClient
) -> List[Dict[str, Any]]:
    formats = []
    video_entries = []
    hls_url = None

    for v_key, v_data in video_list.items():
        v_url = v_data.get("url", "")
        if not v_url:
            continue
        width = v_data.get("width", 0)
        height = v_data.get("height", 0)

        if v_url.endswith(".m3u8"):
            hls_url = v_url
            continue

        video_entries.append({"key": v_key, "url": v_url, "width": width, "height": height})

    video_entries.sort(key=lambda x: x["height"], reverse=True)
    seen_heights = set()
    for entry in video_entries:
        h = entry["height"]
        if h in seen_heights:
            continue
        seen_heights.add(h)
        formats.append({
            "quality": f"{h}p" if h else entry["key"],
            "resolution": f"{entry['width']}x{h}" if h else None,
            "url": entry["url"],
            "format": "mp4",
        })

    if not formats and hls_url:
        hls_formats = await _parse_hls_formats(hls_url, client)
        if hls_formats:
            formats.extend(hls_formats)

    return formats


def _extract_duration(video_list: Dict[str, Any]) -> Optional[str]:
    for v_data in video_list.values():
        dur_ms = v_data.get("duration", 0)
        if dur_ms > 0:
            secs = dur_ms // 1000
            mins = secs // 60
            return f"{mins}:{secs % 60:02d}"
    return None


async def extract_pinterest(url: str) -> Dict[str, Any]:
    """
    Extract video/image from Pinterest using internal PinResource API.

    Note: Video download URLs (.pinimg.com) require
          `Referer: https://www.pinterest.com/` header.
    """
    logger.info(f"Extracting Pinterest pin: {url}")

    async with httpx.AsyncClient(
        headers=HEADERS.copy(), follow_redirects=True, timeout=30.0
    ) as client:
        if "pin.it" in url:
            url = await _resolve_short_url(url)

        pin_id = _extract_pin_id(url)
        if not pin_id:
            raise ValueError("Could not extract pin ID from URL")

        csrf_token = await _get_csrf_token(client)

        params = {
            "source_url": f"/pin/{pin_id}/",
            "data": json.dumps({
                "options": {"id": pin_id, "field_set_key": "detailed"},
                "context": {},
            }),
        }

        api_headers = {**HEADERS, "X-CSRFToken": csrf_token}
        resp = await client.get(PIN_API_URL, params=params, headers=api_headers)
        resp.raise_for_status()

        data = resp.json()
        pin_data = data.get("resource_response", {}).get("data")
        if not pin_data:
            raise ValueError("Pin not found or data unavailable")

        title = (
            pin_data.get("grid_title") or pin_data.get("title")
            or pin_data.get("description", "")[:80] or "Pinterest Pin"
        )
        title = re.sub(r"\s+", " ", title).strip()

        images = pin_data.get("images") or {}
        thumbnail = None
        for key in ("orig", "736x", "564x", "474x"):
            if images.get(key, {}).get("url"):
                thumbnail = images[key]["url"]
                break

        pinner = pin_data.get("pinner") or {}
        author = pinner.get("full_name") or pinner.get("username")

        formats = []
        duration = None

        # Source 1: Top-level videos
        videos = pin_data.get("videos") or {}
        video_list = videos.get("video_list") or {}
        if video_list:
            formats = await _extract_formats_from_video_list(video_list, client)
            duration = _extract_duration(video_list)

        # Source 2: Story/Idea pins
        if not formats:
            story_data = pin_data.get("story_pin_data") or {}
            pages = story_data.get("pages") or []
            for page in pages:
                blocks = page.get("blocks") or []
                for block in blocks:
                    video_block = block.get("video")
                    if not video_block:
                        continue
                    block_video_list = video_block.get("video_list") or {}
                    if block_video_list:
                        page_formats = await _extract_formats_from_video_list(block_video_list, client)
                        if page_formats:
                            formats.extend(page_formats)
                            if not duration:
                                duration = _extract_duration(block_video_list)

        # Source 3: Embed data
        if not formats:
            embed = pin_data.get("embed") or {}
            embed_url = embed.get("src") or embed.get("url")
            if embed_url and ("video" in embed_url.lower() or "mp4" in embed_url.lower()):
                formats.append({"quality": "Original", "url": embed_url, "format": "mp4"})

        # Fallback: Image pin
        if not formats:
            if thumbnail:
                formats.append({"quality": "Original Image", "url": thumbnail, "format": "jpg"})
            else:
                raise ValueError("Could not find video in this Pinterest pin.")

        return {
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "author": author,
            "formats": formats,
        }
