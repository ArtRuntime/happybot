# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
import re
import yt_dlp
import random
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime

from youtubesearchpython.__future__ import VideosSearch
from ytmusicapi import YTMusic

from bot import logger, config, db
from bot.helpers import Track, utils


class StorageLowError(Exception):
    """Raised when there's not enough storage space for download."""
    pass


class DownloadCancelledError(Exception):
    """Raised when download is cancelled by user."""
    pass


# Track cancelled downloads per chat_id
_cancelled_downloads: set[int] = set()


class YouTube:
    StorageLowError = StorageLowError # Expose exception class 

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
        
        # Initialize ytmusicapi with optional auth
        auth_path = "bot/cookies/browser.json"
        
        try:
            if os.path.exists(auth_path):
                self.ytmusic = YTMusic(auth_path)
                logger.info(f"ytmusicapi initialized in AUTHENTICATED mode (using {auth_path})")
            else:
                self.ytmusic = YTMusic()
                logger.info("ytmusicapi initialized in ANONYMOUS mode (no browser.json found)")
        except Exception as e:
            logger.error(f"Failed to initialize ytmusicapi: {e}")
            self.ytmusic = None


    def cancel_downloads(self, chat_id: int):
        """Mark all downloads for this chat as cancelled."""
        _cancelled_downloads.add(chat_id)
        logger.info(f"Marked downloads cancelled for chat {chat_id}")

    def clear_cancelled(self, chat_id: int):
        """Clear cancelled flag to allow new downloads (after user adds new song)."""
        _cancelled_downloads.discard(chat_id)
        logger.debug(f"Cleared cancelled flag for chat {chat_id}")
    def get_cookies(self):
        # Create cookie directory if it doesn't exist
        os.makedirs(self.cookie_dir, exist_ok=True)
        
        self.cookies = [] # Reset list
        for file in os.listdir(self.cookie_dir):
            if file.endswith(".txt") and "fallback" not in file:
                self.cookies.append(f"{self.cookie_dir}/{file}")
        
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
            
        return random.choice(self.cookies)

    def _get_fallback_cookie(self) -> str | None:
        """Get the path to the fallback cookie file if it exists."""
        path = f"{self.cookie_dir}/cookie_fallback.txt"
        if os.path.exists(path):
            return path
        return None


    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies/auth...")
        
        if not (urls or config.BROWSER_JSON_URL):
            return

        # Import aiohttp_socks only if needed to avoid overhead if not using SOCKS
        if config.PROXY_URL and config.PROXY_URL.startswith("socks"):
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(config.PROXY_URL)
            session = aiohttp.ClientSession(connector=connector)
        else:
            session = aiohttp.ClientSession()

        async with session:
            # Prepare proxy args for http requests
            kwargs = {}
            if config.PROXY_URL and not config.PROXY_URL.startswith("socks"):
                kwargs["proxy"] = config.PROXY_URL

            # 1. Download browser.json if configured
            if config.BROWSER_JSON_URL:
                try:
                    logger.info(f"Downloading browser.json from URL...")
                    async with session.get(config.BROWSER_JSON_URL, **kwargs) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            auth_path = "bot/cookies/browser.json"
                            # Ensure directory exists
                            os.makedirs(os.path.dirname(auth_path), exist_ok=True)
                            with open(auth_path, "wb") as f:
                                f.write(content)
                            logger.info("Updated browser.json")
                            
                            # Re-init ytmusicapi
                            try:
                                self.ytmusic = YTMusic(auth_path)
                                logger.info("Reloaded ytmusicapi with new auth")
                            except Exception as exc:
                                logger.error(f"Failed to reload ytmusicapi: {exc}")
                        else:
                            logger.error(f"Failed to download browser.json: HTTP {resp.status}")
                except Exception as e:
                    logger.error(f"Error downloading browser.json: {e}")

            # 2. Download cookies.txt files
            if urls:
                for i, url in enumerate(urls):
                    path = f"{self.cookie_dir}/cookie_{i}.txt"
                    if "batbin" in url:
                        link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                    else:
                        link = url
                    try:
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
        """Search YouTube Music for a query using ytmusicapi."""
        if "music.youtube.com" in query:
            query = query.replace("music.youtube.com", "www.youtube.com")


        # If it's a YouTube URL, use generic search to get exact video
        if self.valid(query):
            return await self._generic_search(query, m_id, video)
        
        # If it's any other URL, use generic search
        if query.startswith("http"):
            return await self._generic_search(query, m_id, video)
        
        if not self.ytmusic:
            logger.error("ytmusicapi not initialized")
            return None
        
        try:
            # Set proxy env locally for httpx
            if config.PROXY_URL:
                os.environ['HTTP_PROXY'] = config.PROXY_URL
                os.environ['HTTPS_PROXY'] = config.PROXY_URL

            # Search using youtube-search-python
            search = VideosSearch(query, limit=1)
            results = await search.next()
            
            # Clean up immediately
            if config.PROXY_URL:
                os.environ.pop('HTTP_PROXY', None)
                os.environ.pop('HTTPS_PROXY', None)
            
            if not results or not results.get('result'):
                logger.warning("No playable result found in search")
                return None
                
            data = results['result'][0]
            video_id = data.get('id')
            
            title = data.get('title')
            if not title: title = "Unknown Title"
            
            # Extract duration safely
            duration = data.get('duration')
            if not duration: duration = "0:00"
            
            # Extract channel safely (handle None for 'channel' key)
            channel_data = data.get('channel') or {}
            channel_name = channel_data.get('name') or "Unknown"
            
            # Extract thumbnail safely (handle None for 'thumbnails' key)
            thumbnails = data.get('thumbnails') or []
            thumbnail = thumbnails[-1].get('url', "") if (isinstance(thumbnails, list) and thumbnails) else None
            
            # Safe view count extraction
            wc_data = data.get('viewCount') or {}
            view_count = wc_data.get('short') or ""
            
            return Track(
                id=str(video_id) if video_id else "",
                channel_name=str(channel_name),
                duration=str(duration),
                duration_sec=utils.to_seconds(str(duration)),
                message_id=m_id,
                title=str(title)[:50],
                thumbnail=thumbnail,
                url=f"https://www.youtube.com/watch?v={video_id}",
                view_count=str(view_count),
                video=video,
            )
        except Exception as e:
            # youtube-search-python sometimes throws a TypeError when channel.id is None:
            # "can only concatenate str (not 'NoneType') to str". Treat it as a soft failure
            # and avoid spamming full tracebacks in logs.
            msg = str(e)
            if isinstance(e, TypeError) and "can only concatenate str (not \"NoneType\") to str" in msg:
                logger.warning("py-yt-search hit known channel.id None bug; skipping to fallback.")
            else:
                logger.error(f"py-yt-search failed: {e}", exc_info=True)
            
            # Fallback 1: YouTube Music (ytmusicapi)
            logger.info(f"Falling back to ytmusicapi for: {query}")
            try:
                if self.ytmusic:
                    # Inject proxy to ytmusicapi session
                    if config.PROXY_URL:
                        if not hasattr(self.ytmusic, '_session') or not self.ytmusic._session:
                            import requests
                            self.ytmusic._session = requests.Session()
                        self.ytmusic._session.proxies.update({
                            "http": config.PROXY_URL,
                            "https": config.PROXY_URL
                        })
                        
                    results = await asyncio.to_thread(
                        self.ytmusic.search, query, filter="songs", limit=1
                    )
                    
                    if results and len(results) > 0:
                        data = results[0]
                        video_id = data.get('videoId')
                        
                        if video_id:
                            # Extract artist name
                            artists = data.get('artists', [])
                            channel_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'
                            
                            # Get duration
                            duration = data.get('duration', '0:00') or '0:00'
                            
                            # Get thumbnail
                            thumbnails = data.get('thumbnails', [])
                            thumbnail = thumbnails[-1].get('url') if thumbnails else None
                            
                            logger.info(f"✅ ytmusicapi fallback success: {data.get('title')}")
                            return Track(
                                id=video_id,
                                channel_name=str(channel_name),
                                duration=str(duration),
                                duration_sec=utils.to_seconds(str(duration)),
                                message_id=m_id,
                                title=str(data.get('title', 'Unknown'))[:50],
                                thumbnail=thumbnail,
                                url=f"https://www.youtube.com/watch?v={video_id}",
                                view_count='',
                                video=video,
                            )
            except Exception as ytm_err:
                logger.warning(f"ytmusicapi fallback failed: {ytm_err}")
            
            # Fallback 2: yt-dlp search
            logger.info(f"Falling back to yt-dlp search for: {query}")
            try:
                cookie = self.get_cookies()
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "nocheckcertificate": True,
                    "noplaylist": True, # We only want the first result
                    "flat_playlist": True, # Don't extract full details yet/fast
                }
                if cookie: ydl_opts["cookiefile"] = cookie
                if config.PROXY_URL: ydl_opts["proxy"] = config.PROXY_URL
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # ytsearch1: returns 1 result
                    info = await asyncio.to_thread(ydl.extract_info, f"ytsearch1:{query}", download=False)
                    
                    if info and 'entries' in info and info['entries']:
                        entry = info['entries'][0]
                        video_id = entry.get('id')
                        return Track(
                            id=video_id,
                            channel_name=entry.get('uploader', 'Unknown'),
                            duration=str(entry.get('duration', "0:00")),
                            duration_sec=int(entry.get('duration', 0) or 0),
                            message_id=m_id,
                            title=entry.get('title', 'Unknown Title')[:50],
                            thumbnail=None, # flat_playlist doesn't always give thumbs
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            view_count=str(entry.get('view_count', '')),
                            video=video,
                        )
            except Exception as ex:
                logger.error(f"yt-dlp fallback search failed: {ex}")
        
        return None

    async def _generic_search(self, url: str, m_id: int, video: bool = False) -> Track | None:
        """Helper to extract info from generic URLs using yt-dlp"""
        cookie = self.get_cookies()
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
        }
        if cookie:
            ydl_opts["cookiefile"] = cookie
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                except Exception as ex:
                    # Retry with fallback cookie if Sign in error
                    if "Sign in to confirm" in str(ex):
                        fallback = self._get_fallback_cookie()
                        if fallback:
                            logger.warning("_generic_search: Primary cookie failed. Retrying with fallback...")
                            ydl_opts["cookiefile"] = fallback
                            try:
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl_fallback:
                                    info = await asyncio.to_thread(ydl_fallback.extract_info, url, download=False)
                                    logger.info("✅ Fallback cookie success (search)!")
                            except Exception as ex2:
                                if "Sign in to confirm" in str(ex2):
                                    logger.warning("_generic_search: Fallback cookie failed. Retrying cookie-less (Android + Proxy)...")
                                    # Cookie-less Fallback
                                    ydl_opts.pop("cookiefile", None)
                                    ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                                    if config.PROXY_URL:
                                        ydl_opts["proxy"] = config.PROXY_URL
                                    
                                    with yt_dlp.YoutubeDL(ydl_opts) as ydl_less:
                                        info = await asyncio.to_thread(ydl_less.extract_info, url, download=False)
                                        logger.info("✅ Cookie-less fallback success (search)!")
                                else:
                                    raise ex2
                        else:
                            # Direct check for cookie-less if no fallback exists
                            logger.warning("_generic_search: Primary failed and no fallback. Retrying cookie-less...")
                            ydl_opts.pop("cookiefile", None)
                            ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                            if config.PROXY_URL:
                                ydl_opts["proxy"] = config.PROXY_URL
                            
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl_less:
                                info = await asyncio.to_thread(ydl_less.extract_info, url, download=False)
                                logger.info("✅ Cookie-less fallback success (search)!")
                    else:
                        raise ex
                
            if not info:
                return None

            # Extract video ID for autoplay support
            video_id = info.get("id") or url
            
            # Determine req_type for autoplay eligibility
            # Use yt-dlp's extractor info to accurately detect YouTube
            extractor = info.get("extractor", "").lower()
            req_type = "generic"  # Default: no autoplay
            
            # For YouTube sources, use short video ID; for others, use full URL
            # This ensures download() uses the correct URL for non-YouTube sources
            is_youtube = extractor in ["youtube", "youtube:tab", "youtube:playlist"]
            
            if is_youtube:
                # Check if URL is from YouTube (not just YouTube content embedded elsewhere)
                if "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url:
                    req_type = "youtube"
                    track_id = video_id  # Use short ID for YouTube
                else:
                    req_type = "generic"
                    track_id = url  # Use full URL for embedded YouTube content
                    logger.info(f"Non-YouTube URL with YouTube content - using full URL")
            else:
                # For non-YouTube sources (Instagram, etc.), always use original URL
                track_id = url
                logger.info(f"Non-YouTube source ({extractor}) - using full URL for download")

            # Get duration from yt-dlp (returns seconds) and format it
            duration_sec = int(info.get("duration", 0) or 0)

            # Fallback: if duration is 0 (common for direct URLs), try ffprobe
            if duration_sec == 0:
                duration_sec = await utils.get_duration(url)
                logger.info(f"Refetched duration via ffprobe: {duration_sec}s")

            if duration_sec:
                hours = duration_sec // 3600
                mins = (duration_sec % 3600) // 60
                secs = duration_sec % 60
                if hours > 0:
                    duration = f"{hours}:{mins:02d}:{secs:02d}"
                else:
                    duration = f"{mins}:{secs:02d}"
            else:
                duration = "0:00"

            return Track(
                id=track_id,  # Use full URL for non-YouTube, short ID for YouTube
                channel_name=info.get("uploader", "Unknown"),
                duration=duration,
                duration_sec=duration_sec,
                message_id=m_id,
                title=info.get("title", "Unknown")[:25],
                thumbnail=info.get("thumbnail"),
                url=url,
                view_count=str(info.get("view_count", "")),
                video=video,
                req_type=req_type,  # Set req_type for autoplay eligibility
            )
        except Exception as e:
            logger.error(f"Generic search failed: {e}")
            return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        """Get playlist tracks using ytmusicapi."""
        tracks = []
        
        if not self.ytmusic:
            logger.error("ytmusicapi not initialized")
            return tracks
        
        try:
            # Extract playlist ID from URL
            import re
            match = re.search(r'list=([A-Za-z0-9_-]+)', url)
            if not match:
                logger.error(f"Could not extract playlist ID from: {url}")
                return tracks
            
            playlist_id = match.group(1)
            logger.info(f"Fetching playlist: {playlist_id}")
            
            # Get playlist using ytmusicapi
            # Use limit=None for unlimited if limit <= 0
            api_limit = limit if limit > 0 else None
            
            playlist_data = await asyncio.to_thread(
                self.ytmusic.get_playlist,
                playlist_id,
                limit=api_limit
            )
            
            if not playlist_data or 'tracks' not in playlist_data:
                logger.warning("No tracks found in playlist (ytmusicapi). Falling back to yt-dlp...")
                return await self._generic_playlist(url, limit, user, video)
            
            # Slice only if limit is set
            raw_tracks = playlist_data['tracks']
            if limit > 0:
                raw_tracks = raw_tracks[:limit]
            
            for data in raw_tracks:
                if not data:
                    continue
                
                video_id = data.get("videoId")
                if not video_id:
                    continue
                
                # Extract artist name
                artists = data.get("artists", [])
                channel_name = artists[0].get("name") if artists else ""
                
                # Get duration
                duration = data.get("duration", "0:00")
                if not duration:
                    duration = "0:00"
                
                # Get thumbnail - preserve full URL
                thumbnails = data.get("thumbnails", [])
                thumbnail = thumbnails[-1].get("url", "") if thumbnails else None
                
                track = Track(
                    id=video_id,
                    channel_name=channel_name,
                    duration=duration,
                    duration_sec=utils.to_seconds(duration),
                    title=data.get("title", "Unknown")[:25],
                    thumbnail=thumbnail,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
                
            logger.info(f"Loaded {len(tracks)} tracks from playlist")
            
            if not tracks:
                 logger.warning("ytmusicapi returned tracks but parsing failed. Falling back to yt-dlp...")
                 return await self._generic_playlist(url, limit, user, video)
        except Exception as e:
            logger.error(f"ytmusicapi Playlist error: {e}")
            logger.info("Falling back to yt-dlp for playlist...")
            return await self._generic_playlist(url, limit, user, video)
        
        return tracks

    async def _generic_playlist(self, url: str, limit: int, user: str, video: bool) -> list[Track | None]:
        """Helper to fetch playlist using yt-dlp."""
        tracks = []
        cookie = self.get_cookies()
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extract_flat": True,  # Fast extraction
        }
        
        # Only set limit if it's positive
        if limit > 0:
            ydl_opts["playlistend"] = limit
            
        if cookie:
            ydl_opts["cookiefile"] = cookie
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                except Exception as ex:
                    # Retry with fallback cookie if Sign in error
                    if "Sign in to confirm" in str(ex):
                        fallback = self._get_fallback_cookie()
                        if fallback:
                            logger.warning("_generic_playlist: Primary cookie failed. Retrying with fallback...")
                            ydl_opts["cookiefile"] = fallback
                            try:
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl_fallback:
                                    info = await asyncio.to_thread(ydl_fallback.extract_info, url, download=False)
                                    logger.info("✅ Fallback cookie success (playlist)!")
                            except Exception as ex2:
                                if "Sign in to confirm" in str(ex2):
                                    logger.warning("_generic_playlist: Fallback cookie failed. Retrying cookie-less (Android + Proxy)...")
                                    ydl_opts.pop("cookiefile", None)
                                    ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                                    if config.PROXY_URL:
                                        ydl_opts["proxy"] = config.PROXY_URL
                                    
                                    with yt_dlp.YoutubeDL(ydl_opts) as ydl_less:
                                        info = await asyncio.to_thread(ydl_less.extract_info, url, download=False)
                                        logger.info("✅ Cookie-less fallback success (playlist)!")
                                else:
                                    raise ex2
                        else:
                            logger.warning("_generic_playlist: Primary failed and no fallback. Retrying cookie-less...")
                            ydl_opts.pop("cookiefile", None)
                            ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                            if config.PROXY_URL:
                                ydl_opts["proxy"] = config.PROXY_URL
                            
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl_less:
                                info = await asyncio.to_thread(ydl_less.extract_info, url, download=False)
                                logger.info("✅ Cookie-less fallback success (playlist)!")
                    else:
                        raise ex
                
            if not info:
                return tracks

            entries = info.get('entries', [])
            for data in entries:
                if not data:
                    continue
                    
                tracks.append(Track(
                    id=data.get("id"),
                    channel_name=data.get("uploader", "Unknown"),
                    duration=str(data.get("duration", 0)),
                    duration_sec=data.get("duration", 0),
                    title=data.get("title", "Unknown")[:25],
                    thumbnail=None, # flat extraction often doesn't give thumbs, but lightweight
                    url=data.get("url") or f"https://www.youtube.com/watch?v={data.get('id')}",
                    user=user,
                    view_count="",
                    video=video,
                ))
            
            logger.info(f"yt-dlp: Loaded {len(tracks)} tracks from playlist")
                
        except Exception as e:
            logger.error(f"Generic playlist error: {e}")
            
        return tracks


    class YtDlpLogger:
        def debug(self, msg):
            if config.YTDLP_VERBOSE and not msg.startswith('[debug] '):
                logger.info(f"yt-dlp: {msg}")
        def info(self, msg):
            if config.YTDLP_VERBOSE:
                logger.info(f"yt-dlp: {msg}")
        def warning(self, msg):
            if config.YTDLP_VERBOSE:
                logger.warning(f"yt-dlp: {msg}")
        def error(self, msg):
            # Always show errors, they're critical
            logger.error(f"yt-dlp: {msg}")

    async def download(self, video_id: str, video: bool = False) -> str | None:
        if video_id.startswith("http"):
            url = video_id
            # Use MD5 hash of URL for safer and unique filenames
            import hashlib
            safe_id = hashlib.md5(url.encode()).hexdigest()
            file_name_base = safe_id
        else:
            url = self.base + video_id
            file_name_base = video_id
            
        os.makedirs("downloads", exist_ok=True)


        # Check for existing file with any common extension

        for ext in [".mp4", ".mkv", ".webm", ".m4a", ".mp3"]:
             path = f"downloads/{file_name_base}{ext}"
             if Path(path).exists():
                 return path

        # ---------------------------------------------------------
        # yt-dlp Download (Primary Method)
        # ---------------------------------------------------------

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": f"downloads/{file_name_base}.%(ext)s",
            "quiet": False,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": False,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
            "logger": self.YtDlpLogger(),  # Use custom logger

        }
        

        if video:
            ydl_opts = {
                **base_opts,
                # Ensure video + audio are both downloaded and merged
                # Priority: best video+audio merge, then best pre-merged, then any best
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                "merge_output_format": "mp4",  # Force merge to mp4 for compatibility
                "audio_multistreams": True,  # Keep all audio tracks
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio/best",
                "audio_multistreams": True, # Keep all audio tracks
            }

        def _download():
            logger.info(f"Starting download for {url}")
            try:
                # Check available storage before downloading
                import shutil
                disk_usage = shutil.disk_usage("/")
                free_space = disk_usage.free
                
                # Get expected file size first and check if it fits
                with yt_dlp.YoutubeDL({"quiet": True, "geo_bypass": True, "nocheckcertificate": True}) as ydl_info:
                    try:
                        info = ydl_info.extract_info(url, download=False)
                        filesize = info.get("filesize") or info.get("filesize_approx") or 0
                        
                        # Check if file size fits in available space
                        if filesize > 0 and filesize > free_space:
                            logger.warning(f"Not enough storage! File: {filesize // (1024*1024)} MB, Available: {free_space // (1024*1024)} MB")
                            raise StorageLowError(f"File: {filesize // (1024*1024)} MB, Available: {free_space // (1024*1024)} MB")
                        elif filesize > 0:
                            logger.info(f"Storage OK. File: {filesize // (1024*1024)} MB, Available: {free_space // (1024*1024)} MB")
                    except StorageLowError:
                        raise
                    except:
                        pass  # Continue if metadata fetch fails
                
                logger.info(f"Using options: {ydl_opts}")
                
                # Try primary download
                downloaded_path = None
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                    # Find the downloaded file
                    for file in os.listdir("downloads"):
                        if file.startswith(file_name_base):
                            downloaded_path = f"downloads/{file}"
                            break
                            
                    return downloaded_path
                except Exception as ex:
                    # Check for Sign in error and retry with fallback
                    if "Sign in to confirm" in str(ex):
                        fallback = self._get_fallback_cookie()
                        
                        if fallback:
                            logger.warning("Primary cookie failed with Sign-in error. Retrying with fallback cookie...")
                            ydl_opts["cookiefile"] = fallback
                            try:
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([url])
                                logger.info("✅ Fallback cookie success!")
                                
                                # Find file
                                for file in os.listdir("downloads"):
                                    if file.startswith(file_name_base):
                                        return f"downloads/{file}"
                            except Exception as ex2:
                                logger.error(f"Fallback cookie also failed: {ex2}")
                                if "Sign in to confirm" not in str(ex2):
                                    return None
                        
                        # Cookie-less Fallback (Third Layer)
                        logger.warning("Primary/Fallback failed. Retrying cookie-less (Android + Proxy)...")
                        ydl_opts.pop("cookiefile", None)
                        ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                        if config.PROXY_URL:
                            ydl_opts["proxy"] = config.PROXY_URL
                            
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                            logger.info("✅ Cookie-less fallback success!")
                            # Find file
                            for file in os.listdir("downloads"):
                                if file.startswith(file_name_base):
                                    return f"downloads/{file}"
                        except Exception as ex3:
                            logger.error(f"Cookie-less fallback failed: {ex3}")
                            return None
                    
                    logger.error(f"yt-dlp Execution Error: {ex}")
                    if cookie: self.cookies.remove(cookie)
                    
            except Exception as e:
                logger.error(f"yt-dlp Initialization Error: {e}")

            return None

        # Run yt-dlp in thread
        file_path = await asyncio.to_thread(_download)
        
        if file_path:
            return file_path

        # ---------------------------------------------------------
        # InnerTube Download (Fallback)
        # ---------------------------------------------------------
        if not video_id.startswith("http"):
            try:
                from .innertube import innertube
                logger.info(f"yt-dlp failed using InnerTube Fallback for {video_id}...")
                path = await innertube.download(video_id, filename)
                if path:
                    logger.info(f"✅ InnerTube Fallback Success: {path}")
                    return path
            except Exception as e:
                logger.error(f"InnerTube Fallback Error: {e}")

        return None
    
    async def _check_url_alive(self, url: str) -> bool:
        """Passive check if URL is reachable via HEAD request."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=5, allow_redirects=True) as resp:
                    return resp.status in [200, 302]
        except:
            return False

    async def get_stream_url(self, video_id: str, video: bool = False, quality: str = None) -> str | None:
        """
        Get direct stream URL without downloading (for instant playback).
        
        Args:
            video_id: YouTube video ID or URL
            video: Whether to get video stream (True) or audio stream (False)
        
        Returns:
            Direct HTTP/HTTPS stream URL, or None if failed
        """
        if video_id.startswith("http"):
            url = video_id
        else:
            url = self.base + video_id
            
        # ---------------------------------------------------------
        # 1. MongoDB Cache Check
        # ---------------------------------------------------------
        try:
            # Use video_id as key if it's not a URL, else hash or use full URL
            # For simplicity, we only cache strictly by video ID if available
            cache_key = video_id if not video_id.startswith("http") else None
            
            if cache_key:
                cached = await db.get_stream_cache(cache_key)
                if cached:
                    import time
                    expire = cached.get("expire", 0)
                    now = int(time.time())
                    
                    # Check URL expiration (with 5 min buffer)
                    if expire > (now + 300):
                        # Verify liveness passively
                        if await self._check_url_alive(cached["url"]):
                            logger.info(f"✅ Using cached stream URL for {video_id}")
                            return cached["url"]
                        else:
                            logger.warning(f"Cached URL dead for {video_id}, refreshing...")
                    else:
                        logger.info(f"Cached URL expired for {video_id}, refreshing...")
        except Exception as e:
            logger.error(f"Cache check failed: {e}")

        # ---------------------------------------------------------
        # 2. Extract New URL (Primary: yt-dlp)
        # ---------------------------------------------------------
        
        cookie = self.get_cookies()
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "geo_bypass": True,
        }
        if cookie:
            ydl_opts["cookiefile"] = cookie
        if config.PROXY_URL:
            ydl_opts["proxy"] = config.PROXY_URL
        
        # Select format
        if video:
            # For video: get best quality video+audio
            ydl_opts["format"] = "best"
        else:
            # For audio: get best audio
            # Prefer m4a/opus, fallback to any audio for default from now as fallback
            if not quality:
                quality = getattr(config, 'STREAM_QUALITY', 'medium')
            
            if quality == 'low':
                ydl_opts["format"] = "worstaudio/worst"
            elif quality == 'high' or quality == 'studio':
                ydl_opts["format"] = "bestaudio/best"
            else:  # medium (default)
                ydl_opts["format"] = "bestaudio[abr<=192]/bestaudio/best"
        
        try:
            logger.info(f"Extracting stream URL for {url}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info without downloading
                try:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                except Exception as ex:
                    # Retry with fallback cookie if Sign in error
                    if "Sign in to confirm" in str(ex):
                        fallback = self._get_fallback_cookie()
                        if fallback:
                            logger.warning("get_stream_url: Primary cookie failed. Retrying with fallback...")
                            ydl_opts["cookiefile"] = fallback
                            try:
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl_fallback:
                                    info = await asyncio.to_thread(ydl_fallback.extract_info, url, download=False)
                                    logger.info("✅ Fallback cookie success (stream)!")
                            except Exception as ex2:
                                if "Sign in to confirm" in str(ex2):
                                    logger.warning("get_stream_url: Fallback cookie failed. Retrying cookie-less (Android + Proxy)...")
                                    ydl_opts.pop("cookiefile", None)
                                    ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                                    if config.PROXY_URL:
                                        ydl_opts["proxy"] = config.PROXY_URL
                                    
                                    with yt_dlp.YoutubeDL(ydl_opts) as ydl_less:
                                        info = await asyncio.to_thread(ydl_less.extract_info, url, download=False)
                                        logger.info("✅ Cookie-less fallback success (stream)!")
                                else:
                                    raise ex2
                        else:
                            logger.warning("get_stream_url: Primary failed and no fallback. Retrying cookie-less...")
                            ydl_opts.pop("cookiefile", None)
                            ydl_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
                            if config.PROXY_URL:
                                ydl_opts["proxy"] = config.PROXY_URL
                            
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl_less:
                                info = await asyncio.to_thread(ydl_less.extract_info, url, download=False)
                                logger.info("✅ Cookie-less fallback success (stream)!")
                    else:
                        raise ex
                
                if not info:
                    logger.error("Could not extract stream info")
                    return None
                
                # Get direct URL
                stream_url = info.get('url')
                
                if not stream_url:
                    logger.error("Could not find suitable stream URL")
                    return None
                    
                # ---------------------------------------------------------
                # 3. Save to Cache
                # ---------------------------------------------------------
                try:
                    import re
                    # Extract 'expire' timestamp from URL
                    match = re.search(r'expire=(\d+)', stream_url)
                    if match and not video_id.startswith("http"):
                        expire = int(match.group(1))
                        await db.add_stream_cache(video_id, stream_url, expire)
                        logger.info(f"💾 Saved stream URL to cache for {video_id} (Expires: {expire})")
                except Exception as e:
                    logger.error(f"Failed to save cache: {e}")
                
                logger.info(f"✅ Stream URL extracted (expires in ~6 hours)")
                return stream_url
                    
        except Exception as e:
            logger.error(f"Failed to extract stream URL: {e}")
            if cookie:
                try:
                    self.cookies.remove(cookie)
                except:
                    pass
            if cookie:
                try:
                    self.cookies.remove(cookie)
                except:
                    pass

        if not video_id.startswith("http"):
            if cookie:
                try:
                    self.cookies.remove(cookie)
                except:
                    pass

        return None

    async def smart_autoplay(self, mode: str | bool, previous_track: Track = None) -> Track | None:
        """
        Smart Autoplay using ytmusicapi's get_watch_playlist().
        
        This leverages YouTube Music's intelligent recommendation engine.
        
        Args:
            mode: Autoplay mode (True/'on'/'smart' for auto, or genre name)
            previous_track: Previous track for context
        """
        if not self.ytmusic:
            logger.error("ytmusicapi not initialized")
            return None
        
        try:
            # 1. Handle Genre/Custom Mode (e.g. "Pop", "Rock", "Lofi")
            if isinstance(mode, str) and mode.lower() not in ("smart", "on", "true", "True"):
                logger.info(f"Genre Autoplay: {mode}")
                # Search for genre-based songs
                results = await asyncio.to_thread(
                    self.ytmusic.search,
                    f"{mode} music",
                    # filter="songs", # User requested no filter
                    limit=20
                )
                
                if results:
                    import random
                    selected = random.choice(results)
                    
                    video_id = selected.get('videoId')
                    if video_id:
                        # Extract artist
                        artists = selected.get("artists", [])
                        channel_name = artists[0].get("name") if artists else "Unknown"
                        
                        # Get duration - parse different formats
                        duration = selected.get("duration") or selected.get("length")
                        duration_seconds = None
                        
                        if isinstance(duration, str) and "min" in duration.lower():
                            try:
                                mins = int(duration.lower().replace("min", "").strip())
                                duration_seconds = mins * 60
                            except:
                                pass
                        elif isinstance(duration, int):
                            duration_seconds = duration
                        elif isinstance(duration, str) and ":" in duration:
                            pass  # Already formatted
                        
                        if duration_seconds:
                            hours = duration_seconds // 3600
                            mins = (duration_seconds % 3600) // 60
                            secs = duration_seconds % 60
                            if hours > 0:
                                duration = f"{hours}:{mins:02d}:{secs:02d}"
                            else:
                                duration = f"{mins}:{secs:02d}"
                        else:
                            duration = duration or "0:00"

                        
                        # Thumbnail - preserve full URL
                        thumbnails = selected.get("thumbnails", [])
                        thumbnail = thumbnails[-1].get("url", "") if thumbnails else None
                        
                        return Track(
                            id=video_id,
                            channel_name=channel_name,
                            duration=duration,
                            duration_sec=utils.to_seconds(duration),
                            title=selected.get("title", "Unknown")[:25],
                            thumbnail=thumbnail,
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            user=f"Autoplay ({mode.title()})",
                            view_count="",
                            video=previous_track.video if previous_track else False,
                            req_type="autoplay"
                        )

            # 2. Smart Autoplay (Radio based on previous track)
            if not previous_track or not previous_track.id:
                logger.warning("No previous track for autoplay, using trending")
                return await self._get_trending_track()
            
            # Use ytmusicapi's watch playlist (radio feature)
            logger.info(f"Getting autoplay recommendations for: {previous_track.title}")
            
            watch_data = await asyncio.to_thread(
                self.ytmusic.get_watch_playlist,
                videoId=previous_track.id,
                radio=True,  # Enable radio mode for better variety
                limit=20
            )
            
            if not watch_data or 'tracks' not in watch_data:
                logger.warning("No watch playlist data, falling back to trending")
                return await self._get_trending_track()
            
            tracks = watch_data['tracks']
            if not tracks:
                logger.warning("Empty watch playlist, falling back to trending")
                return await self._get_trending_track()
            
            tracks = [t for t in tracks if t.get('videoId') != previous_track.id]
            if not tracks:
                logger.warning("All tracks were duplicates of previous, falling back to trending")
                return await self._get_trending_track()

            # Pick a random track from top 10 for variety
            import random
            selected = random.choice(tracks[:min(10, len(tracks))])
            
            video_id = selected.get('videoId')
            if not video_id:
                return await self._get_trending_track()
            
            logger.info(f"Autoplay selected: {selected.get('title')}")
            
            # Extract artist name
            artists = selected.get("artists", [])
            channel_name = artists[0].get("name") if artists else "Unknown"
            
            # Get duration - ytmusicapi get_watch_playlist returns 'length' field (in seconds)
            duration = selected.get("duration") or selected.get("length")
            
            # Parse duration - handle different formats
            duration_seconds = None
            
            # Case 1: String with 'min' like "3999 min"
            if isinstance(duration, str) and "min" in duration.lower():
                try:
                    mins = int(duration.lower().replace("min", "").strip())
                    duration_seconds = mins * 60
                except:
                    pass
            # Case 2: Integer (seconds)
            elif isinstance(duration, int):
                duration_seconds = duration
            # Case 3: Already formatted string like "3:45"
            elif isinstance(duration, str) and ":" in duration:
                # Keep as is if already formatted
                pass
            
            # Convert seconds to HH:MM:SS or MM:SS format
            if duration_seconds:
                hours = duration_seconds // 3600
                mins = (duration_seconds % 3600) // 60
                secs = duration_seconds % 60
                if hours > 0:
                    duration = f"{hours}:{mins:02d}:{secs:02d}"
                else:
                    duration = f"{mins}:{secs:02d}"
            elif not duration or duration == "0:00":
                # Fallback: use yt-dlp to get duration
                logger.warning(f"No duration from ytmusicapi, using yt-dlp fallback")
                try:
                    ydl_opts = {"quiet": True, "no_warnings": True}
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, video_url, download=False)
                        if info and info.get("duration"):
                            duration_sec = info.get("duration")
                            mins = duration_sec // 60
                            secs = duration_sec % 60
                            duration = f"{mins}:{secs:02d}"
                        else:
                            duration = "0:00"
                except Exception as e:
                    logger.error(f"yt-dlp duration fallback failed: {e}")
                    duration = "0:00"
            
            # Get thumbnail - preserve full URL
            thumbnails = selected.get("thumbnails", [])
            thumbnail = thumbnails[-1].get("url", "") if thumbnails else None
            
            return Track(
                id=video_id,
                channel_name=channel_name,
                duration=duration,
                duration_sec=utils.to_seconds(duration),
                title=selected.get("title", "Unknown")[:25],
                thumbnail=thumbnail,
                url=f"https://www.youtube.com/watch?v={video_id}",
                user="Autoplay",
                view_count="",
                video=previous_track.video if previous_track else False,
                req_type="autoplay"
            )
            
        except Exception as e:
            logger.error(f"Autoplay failed: {e}")
            return await self._get_trending_track()

    async def _get_trending_track(self) -> Track | None:
        """Fallback: Get a trending track when autoplay fails."""
        if not self.ytmusic:
            return None
        
        try:
            charts = await asyncio.to_thread(
                self.ytmusic.get_charts,
                country='ZZ'  # Global charts
            )
            
            if charts and 'trending' in charts and 'items' in charts['trending']:
                items = charts['trending']['items']
                if items:
                    import random
                    track = random.choice(items[:20])  # Random from top 20
                    
                    video_id = track.get('videoId')
                    if video_id:
                        # Extract artist name
                        artists = track.get("artists", [])
                        channel_name = artists[0].get("name") if artists else "Unknown"
                        
                        # Get duration - parse different formats
                        duration = track.get("duration") or track.get("length")
                        duration_seconds = None
                        
                        if isinstance(duration, str) and "min" in duration.lower():
                            try:
                                mins = int(duration.lower().replace("min", "").strip())
                                duration_seconds = mins * 60
                            except:
                                pass
                        elif isinstance(duration, int):
                            duration_seconds = duration
                        elif isinstance(duration, str) and ":" in duration:
                            pass  # Already formatted
                        
                        if duration_seconds:
                            hours = duration_seconds // 3600
                            mins = (duration_seconds % 3600) // 60
                            secs = duration_seconds % 60
                            if hours > 0:
                                duration = f"{hours}:{mins:02d}:{secs:02d}"
                            else:
                                duration = f"{mins}:{secs:02d}"
                        else:
                            duration = duration or "0:00"

                        
                        # Get thumbnail - preserve full URL
                        thumbnails = track.get("thumbnails", [])
                        thumbnail = thumbnails[-1].get("url", "") if thumbnails else None
                        
                        return Track(
                            id=video_id,
                            channel_name=channel_name,
                            duration=duration,
                            duration_sec=utils.to_seconds(duration),
                            title=track.get("title", "Unknown")[:25],
                            thumbnail=thumbnail,
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            user="Autoplay",
                            view_count="",
                            video=False,
                            req_type="autoplay"
                        )
        except Exception as e:
            logger.error(f"Trending fallback failed: {e}")
        
        return None

    async def autoplay_search(self, query: str, video: bool = False) -> Track | None:
        """Simple search for autoplay (backward compatibility)."""
        return await self.search(query, 0, video)

