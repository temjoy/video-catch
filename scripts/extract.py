#!/usr/bin/env python3
"""
video-catch — Multi-platform video URL extractor.

Usage:
    python extract.py <URL>
    python extract.py "https://www.bilibili.com/video/BV1xx411c7mD"

Outputs JSON with video info and download URLs to stdout.
"""

import asyncio
import json
import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers import extract, detect_platform


async def main():
    if len(sys.argv) < 2:
        print("Usage: python extract.py <URL>", file=sys.stderr)
        print("\nSupported platforms:", file=sys.stderr)
        print("  - Bilibili (bilibili.com, b23.tv)", file=sys.stderr)
        print("  - Douyin (douyin.com, v.douyin.com)", file=sys.stderr)
        print("  - Xiaohongshu (xiaohongshu.com, xhslink.com)", file=sys.stderr)
        print("  - Pinterest (pinterest.com, pin.it)", file=sys.stderr)
        print("  - Vimeo (vimeo.com)", file=sys.stderr)
        print("  - Twitter/X (twitter.com, x.com) — requires yt-dlp", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1].strip()

    # Detect platform first
    platform = detect_platform(url)
    if platform == "unknown":
        print(f"Error: Unsupported URL. Cannot detect platform for: {url}", file=sys.stderr)
        sys.exit(1)

    print(f"Detected platform: {platform}", file=sys.stderr)
    print(f"Extracting...", file=sys.stderr)

    try:
        result = await extract(url)

        # Clean output (remove internal fields)
        for fmt in result.get("formats", []):
            fmt.pop("_segments", None)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except ImportError as e:
        print(f"Error: Missing dependency — {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Extraction failed — {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(asyncio, "run"):
        asyncio.run(main())
    else:
        # Python 3.6 compatibility
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
