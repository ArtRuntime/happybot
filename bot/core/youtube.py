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

from ytmusicapi import YTMusic

from bot import logger, config
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

    def get_cookies(self):
        # Create cookie directory if it doesn't exist
        os.makedirs(self.cookie_dir, exist_ok=True)
        
        self.cookies = [] # Reset list
        for file in os.listdir(self.cookie_dir):
            if file.endswith(".txt"):
                self.cookies.append(f"{self.cookie_dir}/{file}")
        
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
            
        return random.choice(self.cookies)


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
            # Search using ytmusicapi (no filter for broad results)
            results = await asyncio.to_thread(
                self.ytmusic.search,
                query,
                limit=10  # Get multiple results to find a playable one
            )
            
            # Find first result with a videoId (skip albums, artists, playlists)
            data = None
            for result in results:
                if result.get("videoId"):
                    data = result
                    break
            
            if not data:
                logger.warning("No playable result found in search")
                return None

            video_id = data.get("videoId")
            
            # Extract artist name
            artists = data.get("artists", [])
            channel_name = artists[0].get("name") if artists else "Unknown"
            
            # Get duration - parse different formats
            duration = data.get("duration")
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
            thumbnails = data.get("thumbnails", [])
            thumbnail = thumbnails[-1].get("url", "") if thumbnails else None
            
            return Track(
                id=video_id,
                channel_name=channel_name,
                duration=duration,
                duration_sec=utils.to_seconds(duration),
                message_id=m_id,
                title=data.get("title", "Unknown")[:25],
                thumbnail=thumbnail,
                url=f"https://www.youtube.com/watch?v={video_id}",
                view_count="",
                video=video,
            )
        except Exception as e:
            logger.error(f"ytmusicapi search failed: {e}")
        
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
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
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
            duration_sec = info.get("duration", 0)
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
            playlist_data = await asyncio.to_thread(
                self.ytmusic.get_playlist,
                playlist_id,
                limit=limit
            )
            
            if not playlist_data or 'tracks' not in playlist_data:
                logger.warning("No tracks found in playlist")
                return tracks
            
            for data in playlist_data['tracks'][:limit]:
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
            "playlistend": limit,
        }
        if cookie:
            ydl_opts["cookiefile"] = cookie
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
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
            safe_id = video_id.split("/")[-1].split("?")[0]
            if len(safe_id) > 20: safe_id = safe_id[:20]
            filename = f"downloads/{safe_id}.mp4"
        else:
            url = self.base + video_id
            filename = f"downloads/{video_id}.mp4"

        if Path(filename).exists():
            return filename

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": filename,
            "quiet": False,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": False,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
            "logger": self.YtDlpLogger(),  # Use custom logger
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv"],
                }
            },
        }
        
        # Add headers for anime streams to bypass 403 Forbidden
        # Check for common anime CDN domains or any stream URL with master.m3u8
        is_anime_stream = (
            "rainveil" in url or "stormshade" in url or "haildrop" in url or 
            "anime" in url.lower() or "master.m3u8" in url or "/m3u8" in url
        )
        if is_anime_stream:
            base_opts["http_headers"] = {
                "Referer": "https://hianime.to/",
                "Origin": "https://hianime.to",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        ydl.download([url])
                    except Exception as ex:
                        logger.error(f"yt-dlp Execution Error: {ex}")
                        if cookie: self.cookies.remove(cookie)
                        return None
            except Exception as e:
                logger.error(f"yt-dlp Initialization Error: {e}")
                return None
            return filename

        return await asyncio.to_thread(_download)
    
    async def get_stream_url(self, video_id: str, video: bool = False) -> str | None:
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
        
        cookie = self.get_cookies()
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "cookiefile": cookie,
            "sleep_interval": 3,
            "max_sleep_interval": 10,
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv"],
                }
            },
        }
        
        # Use proxy if configured
        if config.PROXY_URL:
            ydl_opts["proxy"] = config.PROXY_URL
        
        # Select format
        if video:
            # For video: get best quality video+audio
            ydl_opts["format"] = "best[ext=mp4]"
        else:
            # For audio: get best audio
            # Prefer m4a/opus, fallback to any audio
            quality = getattr(config, 'STREAM_QUALITY', 'medium')
            if quality == 'low':
                ydl_opts["format"] = "worstaudio/worst"
            elif quality == 'high':
                ydl_opts["format"] = "bestaudio/best"
            else:  # medium (default)
                ydl_opts["format"] = "bestaudio[abr<=192]/bestaudio/best"
        
        try:
            logger.info(f"Extracting stream URL for {url}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info without downloading
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if not info:
                    logger.error("Could not extract stream info")
                    return None
                
                # Get direct URL
                stream_url = info.get('url')
                
                if not stream_url:
                    logger.error("No stream URL found in video info")
                    return None
                
                logger.info(f"✅ Stream URL extracted (expires in ~6 hours)")
                return stream_url
                    
        except Exception as e:
            logger.error(f"Failed to extract stream URL: {e}")
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

