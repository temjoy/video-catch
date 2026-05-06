# Video Catch Skill

This project includes a `video-catch` skill that can parse video download URLs from multiple platforms.

## Quick Usage

```bash
cd scripts/
pip install httpx
python extract.py "VIDEO_URL"
```

## As AI Coding Assistant Skill

This skill works with Claude Code. When you need to extract video URLs, use:

```bash
cd video-catch/scripts
python extract.py "URL"
```

## Supported Platforms

- Bilibili (bilibili.com, b23.tv)
- Douyin (douyin.com, v.douyin.com) — requires China IP or DOUYIN_PROXY
- Xiaohongshu (xiaohongshu.com, xhslink.com)
- Pinterest (pinterest.com, pin.it)
- Vimeo (vimeo.com)
- Twitter/X (twitter.com, x.com) — requires yt-dlp

## Workflow

When a user asks to extract or download a video from a supported platform:

1. Run: `python video-catch/scripts/extract.py "USER_URL"`
2. Parse the JSON output
3. Present available formats to user
4. Download with curl if needed:
   - Bilibili: `curl -L -H "Referer: https://www.bilibili.com/" -o video.mp4 "URL"`
   - Pinterest: `curl -L -H "Referer: https://www.pinterest.com/" -o video.mp4 "URL"`
   - Others: `curl -L -o video.mp4 "URL"`

## Environment Variables

- `DOUYIN_PROXY` — SOCKS5/HTTP proxy for Douyin (needed outside China)
- `TWITTER_COOKIES_FILE` — Netscape cookie file for Twitter (optional)
