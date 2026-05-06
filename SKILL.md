---
name: video-catch
description: Extract video download URLs from Bilibili, Douyin, Xiaohongshu, Pinterest, Vimeo, and Twitter/X. Use when the user provides a video URL and wants to extract or parse video info, get download links, or analyze video metadata. Triggers on phrases like "提取视频", "extract video", "get video URL", "parse video link", "视频下载链接", "解析视频", "get download link", "video info".
---

# Video Catch — Multi-Platform Video URL Extractor

Extract downloadable video URLs from 6 major platforms using native API parsing (no browser required).

## Supported Platforms

| Platform | URL Patterns | Method | Dependencies |
|----------|-------------|--------|--------------|
| **Bilibili** | bilibili.com/video/, b23.tv | Official API | httpx |
| **Douyin** | douyin.com/video/, v.douyin.com | SSR + Web API | httpx |
| **Xiaohongshu** | xiaohongshu.com, xhslink.com | HTML parsing | httpx |
| **Pinterest** | pinterest.com/pin/, pin.it | Internal API + HLS | httpx |
| **Vimeo** | vimeo.com | Player embed config | httpx |
| **Twitter/X** | twitter.com, x.com, t.co | yt-dlp | httpx, yt-dlp |

## Prerequisites

```bash
pip install httpx
# Optional (for Twitter/X only):
pip install yt-dlp
```

## Quick Start

```bash
cd {SKILL_DIR}/scripts
python extract.py "VIDEO_URL"
```

## Usage in Code

```python
import asyncio
from parsers import extract

async def main():
    result = await extract("https://www.bilibili.com/video/BV1xx411c7mD")
    print(result["title"])
    for fmt in result["formats"]:
        print(f"  {fmt['quality']}: {fmt['url']}")

asyncio.run(main())
```

## Output Format

```json
{
  "title": "Video Title",
  "thumbnail": "https://...",
  "duration": "3:45",
  "author": "Author Name",
  "platform": "bilibili",
  "formats": [
    {
      "quality": "1080P",
      "resolution": "1920x1080",
      "fileSize": "45.2MB",
      "url": "https://...",
      "format": "mp4"
    }
  ]
}
```

## Workflow

When a user provides a video URL:

1. **Run the extractor**:
   ```bash
   cd {SKILL_DIR}/scripts
   python extract.py "USER_PROVIDED_URL"
   ```

2. **Parse the JSON output** and present results to user

3. **Download the video** (if user requests):
   ```bash
   # Most platforms — direct download with curl/wget
   curl -L -o "video.mp4" "EXTRACTED_URL"

   # Bilibili — requires Referer header
   curl -L -H "Referer: https://www.bilibili.com/" -o "video.mp4" "EXTRACTED_URL"

   # Pinterest — requires Referer header
   curl -L -H "Referer: https://www.pinterest.com/" -o "video.mp4" "EXTRACTED_URL"

   # Vimeo DASH — use ffmpeg for segment-based streams
   # (progressive URLs work with direct download)
   ```

4. **Handle errors**:
   - Douyin requires mainland China IP → suggest setting `DOUYIN_PROXY` env var
   - Twitter requires yt-dlp → suggest `pip install yt-dlp`
   - Pinterest short links → script handles DNS-over-HTTPS fallback automatically

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `DOUYIN_PROXY` | Proxy for Douyin (needed outside China) | `socks5://user:pass@host:port` |
| `TWITTER_COOKIES_FILE` | Cookie file for Twitter (optional) | `/path/to/cookies.txt` |

## Platform-Specific Notes

### Bilibili
- Download URLs require `Referer: https://www.bilibili.com/` header
- DASH formats are video-only (marked with `videoOnly: true`), need separate audio

### Douyin
- **Requires mainland China IP** or a proxy configured via `DOUYIN_PROXY`
- Returns watermark-free URLs when available

### Pinterest
- HLS streams are automatically parsed to extract direct .cmfv file URLs
- Download URLs require `Referer: https://www.pinterest.com/` header

### Vimeo
- Progressive (direct MP4) URLs returned when available
- DASH formats include segment info in `_segments` field for ffmpeg download

### Twitter/X
- Requires `yt-dlp` package installed
- Optional: set `TWITTER_COOKIES_FILE` for authenticated access

## Example Interactions

User: "帮我提取这个B站视频的下载链接 https://www.bilibili.com/video/BV1xx411c7mD"

```bash
cd {SKILL_DIR}/scripts
python extract.py "https://www.bilibili.com/video/BV1xx411c7mD"
```

User: "Download this Pinterest video: https://pin.it/abc123"

```bash
cd {SKILL_DIR}/scripts
python extract.py "https://pin.it/abc123"
# Then download with:
curl -L -H "Referer: https://www.pinterest.com/" -o "video.mp4" "EXTRACTED_URL"
```
