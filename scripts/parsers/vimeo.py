"""
Vimeo video extractor.

Extracts video info from Vimeo's player embed page (playerConfig).
Returns progressive MP4 direct links when available, or DASH segment info
for manual downloading with ffmpeg.
"""

import asyncio
import json
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _format_filesize(size_bytes: Optional[int]) -> Optional[str]:
    if size_bytes is None or size_bytes <= 0:
        return None
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_duration(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _extract_player_config(html: str) -> Optional[dict]:
    """Extract window.playerConfig JSON from Vimeo embed page."""
    start = html.find("window.playerConfig")
    if start == -1:
        return None
    try:
        brace_start = html.index("{", start)
    except ValueError:
        return None

    depth = 0
    for i in range(brace_start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[brace_start: i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _resolve_base_url(avc_url: str, manifest_base: str) -> str:
    avc_base = avc_url.split("?")[0]
    parts = avc_base.rstrip("/").split("/")[:-1]
    for component in manifest_base.split("/"):
        if component == "..":
            if parts:
                parts.pop()
        elif component and component != ".":
            parts.append(component)
    return "/".join(parts) + "/"


def _build_segment_urls(resolved_base: str, track: dict) -> List[str]:
    track_base = track.get("base_url", "")
    urls = []
    for seg in track.get("segments", []):
        seg_url = seg.get("url", "")
        if seg_url:
            urls.append(resolved_base + track_base + seg_url)
    return urls


def _extract_sync(url: str) -> Dict[str, Any]:
    """Synchronous extraction."""
    video_id = None
    unlisted_hash = None
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)(?:/([a-f0-9]+))?", url)
    if m:
        video_id = m.group(1)
        unlisted_hash = m.group(2)
    if not video_id:
        raise ValueError(f"Could not extract Vimeo video ID from: {url}")

    embed_url = f"https://player.vimeo.com/video/{video_id}"
    if unlisted_hash:
        embed_url += f"?h={unlisted_hash}"

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        resp = client.get(embed_url)
        resp.raise_for_status()
        html = resp.text

    config = _extract_player_config(html)
    if not config:
        raise ValueError("Could not extract playerConfig from Vimeo embed page")

    video_info = config.get("video", {})
    title = video_info.get("title") or "Vimeo Video"
    duration = video_info.get("duration")
    owner = video_info.get("owner", {})
    author = owner.get("name")

    thumbs = video_info.get("thumbs", {})
    thumbnail = (
        video_info.get("thumbnail_url")
        or thumbs.get("1280") or thumbs.get("960")
        or thumbs.get("640") or thumbs.get("base")
    )

    files = config.get("request", {}).get("files", {})

    # Progressive streams (direct MP4 links)
    progressive = files.get("progressive", [])
    if progressive:
        formats = []
        seen = set()
        for p in sorted(progressive, key=lambda x: x.get("height", 0), reverse=True):
            h = p.get("height")
            if not h or h in seen:
                continue
            seen.add(h)
            formats.append({
                "quality": f"{h}p",
                "resolution": f"{p.get('width', '?')}x{h}",
                "fileSize": _format_filesize(p.get("size")),
                "url": p["url"],
                "format": "mp4",
            })
            if len(formats) >= 5:
                break
        if formats:
            return {
                "title": title,
                "thumbnail": thumbnail,
                "duration": _format_duration(duration),
                "author": author,
                "formats": formats,
            }

    # DASH parsing — provide segment info for ffmpeg download
    dash = files.get("dash", {})
    cdns = dash.get("cdns", {})
    if not cdns:
        raise ValueError("No video streams found in Vimeo playerConfig")

    cdn_data = list(cdns.values())[0]
    avc_url = cdn_data.get("avc_url", "") or cdn_data.get("url", "")
    if not avc_url:
        raise ValueError("No AVC URL found in Vimeo DASH config")

    with httpx.Client(
        headers={"User-Agent": HEADERS["User-Agent"]},
        follow_redirects=True, timeout=15,
    ) as client:
        manifest_resp = client.get(avc_url)
        manifest_resp.raise_for_status()
        manifest = manifest_resp.json()

    manifest_base_url = manifest.get("base_url", "")
    resolved_base = _resolve_base_url(avc_url, manifest_base_url)

    video_tracks = manifest.get("video", [])
    audio_tracks = manifest.get("audio", [])

    best_audio = None
    for a in audio_tracks:
        codec = a.get("codecs", "")
        if "mp4a" in codec or "aac" in codec:
            best_audio = a
            break
    if not best_audio and audio_tracks:
        best_audio = audio_tracks[0]

    audio_size = sum(s.get("size", 0) for s in best_audio.get("segments", [])) if best_audio else 0

    formats = []
    seen_heights = set()
    for vt in sorted(video_tracks, key=lambda v: v.get("height", 0), reverse=True):
        height = vt.get("height")
        width = vt.get("width")
        if not height or height in seen_heights or height > 1440:
            continue
        seen_heights.add(height)

        video_size = sum(s.get("size", 0) for s in vt.get("segments", []))
        total_size = video_size + audio_size

        # For DASH, provide metadata — user needs ffmpeg to download
        video_seg_urls = _build_segment_urls(resolved_base, vt)
        audio_seg_urls = _build_segment_urls(resolved_base, best_audio) if best_audio else []

        formats.append({
            "quality": f"{height}p",
            "resolution": f"{width}x{height}" if width else f"{height}p",
            "fileSize": _format_filesize(total_size),
            "url": video_seg_urls[0] if video_seg_urls else "",
            "format": "mp4",
            "dash": True,  # Flag: this needs DASH segment downloading
            "_segments": {
                "video_init": vt.get("init_segment", ""),
                "video_urls": video_seg_urls,
                "audio_init": best_audio.get("init_segment", "") if best_audio else "",
                "audio_urls": audio_seg_urls,
            },
        })
        if len(formats) >= 5:
            break

    if not formats:
        raise ValueError("No video formats found in Vimeo manifest")

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": _format_duration(duration),
        "author": author,
        "formats": formats,
    }


async def extract_vimeo(url: str) -> Dict[str, Any]:
    """Extract video info from Vimeo."""
    logger.info(f"Extracting Vimeo video: {url}")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_sync, url)
