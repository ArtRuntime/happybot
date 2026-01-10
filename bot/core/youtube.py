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
                    if "batbin" in url:
                        link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                    else:
                        link = url
                    try:
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
        if "music.youtube.com" in query:
            query = query.replace("music.youtube.com", "www.youtube.com")

        if hasattr(self, 'regex') and not self.regex.match(query) and query.startswith("http"):
             return await self._generic_search(query, m_id, video)
            
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
            
        # Use proxy_env for yt-dlp generic search
        with proxy_env():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                    
                if not info:
                    return None

                return Track(
                    id=url, 
                    channel_name=info.get("uploader", "Unknown"),
                    duration=str(info.get("duration", 0)), 
                    duration_sec=info.get("duration", 0),
                    message_id=m_id,
                    title=info.get("title", "Unknown")[:25],
                    thumbnail=info.get("thumbnail"),
                    url=url,
                    view_count=str(info.get("view_count", "")),
                    video=video,
                )
            except Exception as e:
                logger.error(f"Generic search failed: {e}")
                return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            # Wrap the API call with temporary proxy env vars
            with proxy_env():
                plist = await Playlist.get(url)
                
            for data in plist["videos"][:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception as e:
            logger.error(f"Playlist error: {e}")
            pass
        return tracks

    class YtDlpLogger:
        def debug(self, msg):
            if not msg.startswith('[debug] '):
                logger.info(f"yt-dlp: {msg}")
        def info(self, msg):
            logger.info(f"yt-dlp: {msg}")
        def warning(self, msg):
            logger.warning(f"yt-dlp: {msg}")
        def error(self, msg):
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
            # Use proxy_env to ensure HTTP proxy is set in environment for yt-dlp
            with proxy_env():
                try:
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

    GENRE_KEYWORDS = {
        "pop": ["pop music 2024", "top pop songs", "pop hits official", "best pop music"],
        "rock": ["rock music official", "rock songs 2024", "classic rock hits", "best rock music"],
        "hiphop": ["hip hop music", "rap songs official", "hip hop 2024", "best rap music"],
        "electronic": ["edm music", "electronic dance music", "house music official", "best edm"],
        "jazz": ["jazz music", "jazz standards", "smooth jazz official", "best jazz"],
        "classical": ["classical music", "classical piano", "orchestra music", "best classical"],
        "metal": ["metal music official", "heavy metal songs", "metal 2024", "best metal"],
        "country": ["country music official", "country songs 2024", "best country music"],
        "rnb": ["r&b music official", "rnb songs 2024", "soul music", "best rnb"],
        "indie": ["indie music official", "indie songs 2024", "alternative music", "best indie"],
        "latin": ["latin music official", "reggaeton 2024", "latin hits", "best latin music"],
        "kpop": ["kpop official mv", "kpop songs 2024", "korean music official", "best kpop"],
        "anime": ["anime opening official", "anime songs official", "anime music 2024", "best anime op"],
        "lofi": ["lofi hip hop music", "lofi beats official", "chill lofi music", "best lofi"],
        "blues": ["blues music official", "blues songs", "blues guitar music", "best blues"],
        "reggae": ["reggae music official", "reggae songs 2024", "best reggae music"],
        "disco": ["disco music official", "disco hits", "best disco music"],
        "punk": ["punk rock official", "punk music 2024", "pop punk songs", "best punk"],
        "ambient": ["ambient music official", "ambient soundscape", "atmospheric music", "best ambient"],
        "random": ["music official video", "top songs 2024", "music video official", "best music"],
    }
    
    BLOCKED_KEYWORDS = [
        "tutorial", "lesson", "course", "learn", "learning",
        "podcast", "interview", "talk", "speech", "lecture",
        "review", "unboxing", "reaction", "gameplay",
        "full movie", "full album", "full episode", "documentary",
        "how to", "guide", "tips", "tricks", "vlog",
        "practice", "exercise", "workout", "meditation",
        "asmr", "story", "audiobook", "compilation",
        " mix", "mix ", "mix-", "mix|", "megami x"
    ]

    # Artist/Channel hints for genre detection
    ARTIST_HINTS = {
        "kpop": ["bts", "blackpink", "twice", "stray kids", "newjeans", "aespa", "itzy", "txt", "enhypen", "ive", "nct", "exo", "red velvet", "seventeen"],
        "anime": ["naruto", "one piece", "demon slayer", "attack on titan", "jujutsu", "my hero", "sword art", "tokyo ghoul", "op/ed", "opening", "ending"],
        "lofi": ["lofi girl", "chillhop", "lofi hip hop", "study beats", "chill beats", "study music"],
        "classical": ["beethoven", "mozart", "chopin", "bach", "vivaldi", "orchestra", "symphony", "piano solo"],
        "hiphop": ["drake", "kendrick", "travis scott", "eminem", "kanye", "jay-z", "50 cent", "lil ", "21 savage", "j cole"],
        "electronic": ["avicii", "marshmello", "deadmau5", "skrillex", "tiesto", "david guetta", "martin garrix", "alan walker"],
        "bollywood": ["arijit", "neha kakkar", "atif aslam", "shreya ghoshal", "kumar sanu", "lata mangeshkar", "kishore kumar", "armaan malik", "jubin nautiyal", "b praak"],
        "punjabi": ["sidhu moose", "ap dhillon", "diljit", "karan aujla", "imran khan", "guru randhawa", "harrdy sandhu"],
    }
    
    # Language hints for detecting song language
    LANGUAGE_HINTS = {
        "hindi": ["hindi", "bollywood", "arijit", "shreya", "neha kakkar", "jubin", "t-series", "zee music", "tips official", "sony music india"],
        "punjabi": ["punjabi", "sidhu", "diljit", "karan aujla", "ap dhillon", "speed records", "geet mp3"],
        "korean": ["korean", "kpop", "k-pop", "bts", "blackpink", "twice", "hybe", "jyp", "sm entertainment", "yg"],
        "japanese": ["japanese", "jpop", "j-pop", "anime", "yoasobi", "kenshi yonezu", "official髭男dism"],
        "spanish": ["spanish", "latino", "reggaeton", "bad bunny", "j balvin", "daddy yankee", "ozuna", "karol g"],
        "english": ["billboard", "vevo", "official video", "lyrics"],  # Default fallback
    }
    
    KEYWORD_SUFFIXES = [
        "music 2024", "songs official", "best songs", "top hits", 
        "playlist 2024", "music video", "new songs", "popular songs"
    ]

    def _detect_genre(self, track: Track) -> tuple[str | None, str | None, str | None]:
        """Detect genre, artist, and language from title and channel."""
        if not track:
            return None, None, None
            
        text = (track.title + " " + (track.channel_name or "")).lower()
        artist = None
        genre = None
        language = None
        
        # Detect language first
        for lang, hints in self.LANGUAGE_HINTS.items():
            for hint in hints:
                if hint in text:
                    language = lang
                    break
            if language:
                break
        
        # Check artist hints (more specific)
        for g, artists in self.ARTIST_HINTS.items():
            for a in artists:
                if a in text:
                    genre = g
                    artist = a
                    break
            if genre:
                break
        
        # Check genre keywords if no artist match
        if not genre:
            for g in self.GENRE_KEYWORDS.keys():
                if g == "random": continue
                if g in text:
                    genre = g
                    break
        
        # Additional heuristics
        if not genre:
            if "rap" in text or "hip hop" in text: genre = "hiphop"
            elif "edm" in text or "house" in text: genre = "electronic"
            elif "rnb" in text or "r&b" in text: genre = "rnb"
            elif "hindi" in text or "bollywood" in text: genre = "bollywood"
            elif "punjabi" in text: genre = "punjabi"
        
        # Extract artist from channel name if not found
        if not artist and track.channel_name:
            artist = track.channel_name.replace(" - Topic", "").replace("VEVO", "").strip()
        
        return genre, artist, language

    def _generate_dynamic_keyword(self, genre: str | None, artist: str | None, language: str | None = None, previous_title: str = None) -> str:
        """Generate a dynamic search keyword based on detected genre/artist/language."""
        import random
        
        # Language-specific prefixes
        lang_prefix = ""
        if language and language != "english":
            lang_prefix = f"{language} "
        
        if artist and len(artist) > 2:
            # Artist-based queries for variety
            artist_queries = [
                f"songs like {artist}",
                f"{artist} type songs",
                f"{lang_prefix}{artist} best songs",
                f"{artist} similar artists",
            ]
            return random.choice(artist_queries)
        
        if genre and genre in self.GENRE_KEYWORDS:
            # Use genre keywords but add variety
            base_keywords = self.GENRE_KEYWORDS[genre]
            suffix = random.choice(self.KEYWORD_SUFFIXES)
            
            # 50% chance to use predefined, 50% to generate dynamic with language
            if random.random() > 0.5:
                return random.choice(base_keywords)
            else:
                return f"{lang_prefix}{genre} {suffix}"
        
        # Language-based fallback if no genre
        if language and language != "english":
            lang_queries = [
                f"{language} songs 2024",
                f"best {language} songs",
                f"{language} music playlist",
                f"new {language} songs",
            ]
            return random.choice(lang_queries)
        
        # Fallback: use previous title keywords if available
        if previous_title:
            # Extract first few words, skip common words
            words = previous_title.lower().split()[:3]
            skip = {"the", "a", "an", "of", "to", "in", "for", "on", "with", "by", "-", "|", "official", "video", "audio", "lyrics"}
            keywords = [w for w in words if w not in skip and len(w) > 2]
            if keywords:
                return f"{lang_prefix}" + " ".join(keywords) + " songs"
        
        # Ultimate fallback
        return random.choice(self.GENRE_KEYWORDS["random"])

    def _is_similar_title(self, title1: str, title2: str) -> bool:
        """Check if two titles are too similar (potential duplicate)."""
        if not title1 or not title2:
            return False
        
        t1 = title1.lower().strip()
        t2 = title2.lower().strip()
        
        # Exact match
        if t1 == t2:
            return True
        
        # One contains the other
        if t1 in t2 or t2 in t1:
            return True
        
        # Check word overlap (if >70% words match, consider similar)
        words1 = set(t1.split())
        words2 = set(t2.split())
        if len(words1) > 0 and len(words2) > 0:
            overlap = len(words1 & words2)
            max_len = max(len(words1), len(words2))
            if overlap / max_len > 0.7:
                return True
        
        return False

    def _is_good_track(self, track_data: dict, previous_title: str = None) -> bool:
        """Filter out bad tracks based on duration, title, and similarity."""
        # Duration check (30s - 600s)
        try:
            duration_str = track_data.get("duration")
            seconds = utils.to_seconds(duration_str)
            if seconds < 30 or seconds > 600:
                return False
        except:
            return False

        title = track_data.get("title", "").lower()
        
        # Blocked keywords
        if any(k in title for k in self.BLOCKED_KEYWORDS):
            return False

        # Duplicate check
        if previous_title and self._is_similar_title(title, previous_title):
            return False
        
        return True

    async def smart_autoplay(self, mode: str | bool, previous_track: Track = None) -> Track | None:
        """
        Smart Autoplay Logic with dynamic keyword generation.
        mode: 'on' (or True), 'smart', or specific genre 'pop', 'rock', etc.
        """
        if mode == True or mode == "on":
             mode = "smart"
             
        genre = None
        artist = None
        language = None
        previous_title = previous_track.title if previous_track else None
        
        # 1. Determine Genre/Artist/Language from previous track
        if mode == "smart" and previous_track:
            genre, artist, language = self._detect_genre(previous_track)
            logger.info(f"Smart Autoplay: Detected genre={genre}, artist={artist}, language={language}")
        elif mode in self.GENRE_KEYWORDS:
            genre = mode
        
        # 2. Generate dynamic keyword
        keyword = self._generate_dynamic_keyword(genre, artist, language, previous_title)
        logger.info(f"Smart Autoplay: Searching '{keyword}' (Genre: {genre}, Artist: {artist}, Lang: {language})")
        
        # 3. Search with retry logic
        for attempt in range(3):
            _search = VideosSearch(keyword, limit=20, with_live=False)
            with proxy_env():
                results = await _search.next()
                
            filtered = []
            if results and results["result"]:
                for res in results["result"]:
                    if self._is_good_track(res, previous_title):
                        filtered.append(res)
            
            if filtered:
                import random
                data = random.choice(filtered)
                return Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name"),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    video=previous_track.video if previous_track else False,
                    req_type="search"
                )
            
            # If no results passed filter, regenerate keyword and retry
            keyword = self._generate_dynamic_keyword(genre, artist, language, previous_title)

        return None

    # Keep old method for backward compat or fallback
    async def autoplay_search(self, query: str, video: bool = False) -> Track | None:
        # Search for the same title but get a few results
        # We'll pick the 2nd result to pretend it's "next"
        # Ideally we'd use related videos but this is a decent heuristic for now
        _search = VideosSearch(query, limit=5, with_live=False)
        
        with proxy_env():
             results = await _search.next()
             
             
        if results and results["result"]:
            # Pick a random result from top 5 to vary the radio
            # If only 1 result, take 0. If more, pick from 0 to min(4, len-1)
            # Avoid picking the exact same title if possible? For now random is enough.
            if len(results["result"]) > 1:
                import random
                index = random.randint(0, min(4, len(results["result"]) - 1))
            else:
                index = 0
            
            data = results["result"][index]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                # No message_id for autoplay usually, handled by caller
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
                req_type="search" # Mark autoplay tracks as search too so they chain!
            )
        return None
