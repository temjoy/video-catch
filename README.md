# video-catch

> 多平台视频链接提取工具 — 从 Bilibili、抖音、小红书、Pinterest、Vimeo、Twitter/X 解析视频下载地址，返回可直接下载的 URL。
>
> Multi-platform video URL extractor — parse video links and return direct download URLs.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 简介

**video-catch** 是一个轻量级的多平台视频链接解析 Skill，通过原生 API 逆向解析（无需浏览器），从视频分享链接中提取可直接下载的视频地址。

### 特性

- **6 大平台**：Bilibili、抖音、小红书、Pinterest、Vimeo、Twitter/X
- **原生解析**：无需浏览器或 Selenium，纯 API 调用
- **极简依赖**：仅需 `httpx`（Twitter 额外需要 `yt-dlp`）
- **多分辨率**：返回所有可用清晰度，按质量排序
- **统一输出**：所有平台返回相同 JSON 格式
- **AI 工具就绪**：支持 CodeBuddy、Claude Code、Cursor、Windsurf 等

### 适用场景

- 设计师/创作者批量收集参考视频素材
- 自动化工作流中的视频下载环节
- AI 编程助手的视频提取能力扩展

---

## Features

- **6 Platforms**: Bilibili, Douyin (抖音), Xiaohongshu (小红书), Pinterest, Vimeo, Twitter/X
- **Native API Parsing**: No browser or headless Chrome needed
- **Lightweight**: Only requires `httpx` (+ optional `yt-dlp` for Twitter)
- **Multi-Quality**: Returns all available resolutions sorted by quality
- **Standardized Output**: Consistent JSON schema across all platforms
- **AI-Tool Ready**: Works as a skill/plugin for CodeBuddy, Claude Code, Cursor, Windsurf, etc.

---

## 快速开始 / Quick Start

```bash
# 安装依赖
pip install httpx

# 提取视频信息
cd scripts/
python extract.py "https://www.bilibili.com/video/BV1xx411c7mD"
```

输出示例 / Output:
```json
{
  "title": "【官方 MV】Never Gonna Give You Up",
  "thumbnail": "https://...",
  "duration": "3:33",
  "author": "索尼音乐中国",
  "platform": "bilibili",
  "formats": [
    {"quality": "720P", "resolution": "1280x720", "fileSize": "49.6MB", "url": "https://...", "format": "mp4"}
  ]
}
```

---

## 安装 / Installation

### 独立使用 / As a standalone tool

```bash
git clone https://github.com/your-username/video-catch.git
cd video-catch
pip install -r requirements.txt
python scripts/extract.py "VIDEO_URL"
```

### 作为 AI Skill / As an AI Skill

将 `video-catch/` 文件夹放入对应目录即可：

| AI 工具 | 放置位置 |
|---------|---------|
| **CodeBuddy** | `skills/video-catch/` |
| **Cursor** | `.cursor/skills/video-catch/` 或项目根目录 |
| **Claude Code** | 项目根目录（读取 `CLAUDE.md`） |
| **Windsurf** | 项目根目录（读取 `.windsurfrules`） |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Codex CLI** | 项目根目录（读取 `AGENTS.md`） |

---

## 支持平台 / Supported Platforms

| 平台 | URL 示例 | 备注 |
|------|----------|------|
| **Bilibili** | `bilibili.com/video/BV...`, `b23.tv/...` | 下载需带 Referer 头 |
| **抖音** | `douyin.com/video/...`, `v.douyin.com/...` | 需中国 IP 或代理 |
| **小红书** | `xiaohongshu.com/explore/...`, `xhslink.com/...` | HTML 页面解析 |
| **Pinterest** | `pinterest.com/pin/...`, `pin.it/...` | HLS → fMP4 提取 |
| **Vimeo** | `vimeo.com/12345` | Progressive MP4 或 DASH |
| **Twitter/X** | `twitter.com/.../status/...`, `x.com/...` | 需要 yt-dlp |

---

## 下载示例 / Download Examples

```bash
# 大多数平台 — 直接下载
curl -L -o "video.mp4" "EXTRACTED_URL"

# Bilibili — 需要 Referer
curl -L -H "Referer: https://www.bilibili.com/" -o "video.mp4" "URL"

# Pinterest — 需要 Referer
curl -L -H "Referer: https://www.pinterest.com/" -o "video.mp4" "URL"
```

---

## Python API

```python
import asyncio
from parsers import extract, detect_platform

async def main():
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    
    # 检测平台
    platform = detect_platform(url)
    print(f"Platform: {platform}")
    
    # 提取视频信息
    result = await extract(url)
    
    print(f"Title: {result['title']}")
    for fmt in result["formats"]:
        print(f"  {fmt['quality']}: {fmt['url'][:80]}...")

asyncio.run(main())
```

---

## 环境变量 / Environment Variables

| 变量 | 用途 | 示例 |
|------|------|------|
| `DOUYIN_PROXY` | 抖音代理（海外部署需要） | `socks5://user:pass@host:port` |
| `TWITTER_COOKIES_FILE` | Twitter Cookie 文件（可选） | `/path/to/cookies.txt` |

---

## 多平台兼容 / Multi-Platform Compatibility

### CodeBuddy
放入 `skills/` 目录，`SKILL.md` 自动识别触发。

### Claude Code
复制 `CLAUDE.md` 到项目根目录，或放入 `.claude/commands/video-catch.md`。

### Cursor
将 `.cursor-rule.mdc` 放入 `.cursor/rules/` 目录。

### Windsurf / Cascade
内容添加到项目根目录的 `.windsurfrules`。

### GitHub Copilot
内容添加到 `.github/copilot-instructions.md`。

### Codex CLI
将 `SKILL.md` 重命名为 `AGENTS.md` 放入 scripts 目录。

---

## 架构 / Architecture

```
video-catch/
├── SKILL.md                 # AI 技能定义（触发词 + 工作流）
├── CLAUDE.md                # Claude Code 适配
├── .cursor-rule.mdc         # Cursor 适配
├── README.md                # 本文件
├── requirements.txt         # Python 依赖
├── LICENSE                  # MIT 许可证
└── scripts/
    ├── extract.py           # CLI 入口
    └── parsers/
        ├── __init__.py      # 包导出
        ├── dispatcher.py    # URL 检测 + 路由
        ├── bilibili.py      # Bilibili API 解析
        ├── douyin.py        # 抖音 SSR + API 解析
        ├── xiaohongshu.py   # 小红书 HTML 解析
        ├── pinterest.py     # Pinterest API + HLS 解析
        ├── vimeo.py         # Vimeo playerConfig 解析
        └── twitter.py       # Twitter via yt-dlp
```

---

## 工作原理 / How It Works

每个解析器使用**原生 API 逆向**而非浏览器自动化：

| 平台 | 解析方式 |
|------|---------|
| Bilibili | 调用官方 `x/web-interface/view` + `x/player/playurl` API |
| 抖音 | 解析 iesdouyin.com 分享页的 SSR `_ROUTER_DATA` |
| 小红书 | 提取页面 `__INITIAL_STATE__` JSON |
| Pinterest | 使用内部 `PinResource/get/` API + HLS m3u8 解析 |
| Vimeo | 获取播放器嵌入页，提取 `window.playerConfig` |
| Twitter | 委托 yt-dlp（唯一外部工具依赖） |

---

## 贡献 / Contributing

1. Fork 仓库
2. 在 `scripts/parsers/` 添加你的解析器
3. 在 `scripts/parsers/dispatcher.py` 中注册
4. 确保返回标准输出格式
5. 提交 PR

### 添加新平台 / Adding a New Platform

```python
# scripts/parsers/my_platform.py
import httpx
from typing import Any, Dict

async def extract_my_platform(url: str) -> Dict[str, Any]:
    """Extract video from MyPlatform."""
    return {
        "title": "...",
        "thumbnail": "...",
        "duration": "...",
        "author": "...",
        "formats": [
            {"quality": "1080p", "url": "...", "format": "mp4"}
        ],
    }
```

---

## 许可证 / License

MIT — 详见 [LICENSE](LICENSE)。

## 致谢 / Credits

Built with love by [@jionghou](https://github.com/jionghou) at ISUX, powered by CodeBuddy.
