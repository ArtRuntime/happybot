# Copyright (c) 2025 botmousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import yt_dlp
import random
import asyncio
import aiohttp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from contextlib import contextmanager

from bot import logger, config
from bot.helpers import Track, utils

@contextmanager
def proxy_env():
    """Context manager to temporarily set proxy env vars for libraries like py_yt that depend on them."""
    if not config.PROXY_URL:
        yield
        return

    # Store old values
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")
    
    # Set new values (py_yt uses httpx which requires HTTP proxy, SOCKS not supported natively in env vars)
    # Since we know Wireproxy provides HTTP on port 40001 (based on generic config), we force that.
    # If the user is using a different proxy setup, this might be fragile, but for this specific "Wireproxy" task it's correct.
    # We'll use 127.0.0.1:40001 if the config points to localhost/socks.
    
    # Set new values (py_yt uses httpx which requires HTTP proxy)
    # Use the same host but the specific HTTP port from config if SOCKS is the main scheme.
    
    proxy_to_use = config.PROXY_URL
    if config.PROXY_SCHEME == "socks5" and config.PROXY_HTTP_PORT:
         # Construct HTTP proxy URL using same host/auth but HTTP port
         if config.PROXY_USERNAME and config.PROXY_PASSWORD:
             proxy_to_use = f"http://{config.PROXY_USERNAME}:{config.PROXY_PASSWORD}@{config.PROXY_HOST}:{config.PROXY_HTTP_PORT}"
         else:
             proxy_to_use = f"http://{config.PROXY_HOST}:{config.PROXY_HTTP_PORT}"
    
    os.environ["HTTP_PROXY"] = proxy_to_use
    os.environ["HTTPS_PROXY"] = proxy_to_use
    
    try:
        yield
    finally:
        # Restore old values
        if old_http is None:
            os.environ.pop("HTTP_PROXY", None)
        else:
            os.environ["HTTP_PROXY"] = old_http
            
        if old_https is None:
            os.environ.pop("HTTPS_PROXY", None)
        else:
            os.environ["HTTPS_PROXY"] = old_https


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "bot/cookies"
        self.warned = False
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

    def get_cookies(self):
        if not self.checked:
            for file in os.listdir(self.cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        
        if config.COOKIES_URL:
            # Import aiohttp_socks only if needed to avoid overhead if not using SOCKS
            if config.PROXY_URL and config.PROXY_URL.startswith("socks"):
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(config.PROXY_URL)
                session = aiohttp.ClientSession(connector=connector)
            else:
                session = aiohttp.ClientSession()

            async with session:
                for i, url in enumerate(urls):
                    path = f"{self.cookie_dir}/cookie_{i}.txt"
                    link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                    try:
                        # Use proxy for HTTP requests if configured (HTTP proxy needs direct passing, SOCKS needs connector)
                        # If SOCKS, connector handles it. If HTTP, we can pass proxy arg or use connector too.
                        # Simplest: If PROXY_URL is set and NOT socks (i.e. http), pass it.
                        kwargs = {}
                        if config.PROXY_URL and not config.PROXY_URL.startswith("socks"):
                            kwargs["proxy"] = config.PROXY_URL
                            
                        async with session.get(link, **kwargs) as resp:
                            resp.raise_for_status()
                            with open(path, "wb") as fw:
                                fw.write(await resp.read())
                    except Exception as e:
                        logger.error(f"Failed to fetch cookie: {e}")
            logger.info(f"Cookies saved in {self.cookie_dir}.")
    
    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        _search = VideosSearch(query, limit=1, with_live=False)
        
        # Wrap the API call with temporary proxy env vars
        with proxy_env():
             results = await _search.next()
             
        if results and results["result"]:
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )
        return None

    # ... (skipping playlist function) ...

    async def download(self, video_id: str, video: bool = False) -> str | None:
        url = self.base + video_id
        ext = "mp4"
        filename = f"downloads/{video_id}.{ext}"

        if Path(filename).exists():
            return filename

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv"],
                }
            },
        }

        if video:
            ydl_opts = {
                **base_opts,
                "format": "best[ext=mp4]",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "best",
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    if cookie: self.cookies.remove(cookie)
                    return None
                except Exception as ex:
                    logger.warning("Download failed: %s", ex)
                    return None
            return filename

        return await asyncio.to_thread(_download)
