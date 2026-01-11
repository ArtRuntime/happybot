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

from py_yt import Playlist, VideosSearch

from contextlib import contextmanager

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
        
        # Initialize TF-IDF recommendation engine
        self.recommender = None
        if config.ENABLE_TFIDF_RECOMMENDATIONS:
            try:
                from bot.core.recommendations import RecommendationEngine
                # Pass MongoDB instance for data storage (with CSV fallback)
                from bot import db
                # db.db is the MongoDB database instance
                mongo_db = getattr(db, 'db', None)
                self.recommender = RecommendationEngine(
                    dataset_path=config.RECOMMENDATION_DATASET_PATH,
                    mongo_db=mongo_db,
                    collection_name="recommendations"
                )
                logger.info("TF-IDF recommendation engine initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize recommendation engine: {e}")
                self.recommender = None

        # Build dynamic keywords on init
        self._build_genre_keywords()

    def cancel_downloads(self, chat_id: int):
        """Mark all downloads for this chat as cancelled."""
        _cancelled_downloads.add(chat_id)
        logger.info(f"Marked downloads cancelled for chat {chat_id}")

    def get_cookies(self):
        # Create cookie directory if it doesn't exist
        os.makedirs(self.cookie_dir, exist_ok=True)
        
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
            
        # Wrap the API call with temporary proxy env vars
        with proxy_env():
             _search = VideosSearch(query, limit=1, with_live=False)
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
            # Use proxy_env to ensure HTTP proxy is set in environment for yt-dlp
            with proxy_env():
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
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv"],
                }
            },
        }
        
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
            
            with proxy_env():
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
                self.cookies.remove(cookie)
            return None

    # --------------------------------------------------------------------------
    # IMPROVED SEARCH LOGIC (2025)
    # --------------------------------------------------------------------------

    GENRE_TERMS = {
        # POP universe
        "pop": ["pop", "pop hits", "top pop", "chart pop", "mainstream pop"],
        "alt_pop": ["alt pop", "alternative pop", "indie pop", "bedroom pop"],
        "hyperpop": ["hyperpop", "digicore", "glitch pop"],

        # ROCK / GUITAR
        "rock": ["rock", "rock hits", "modern rock"],
        "alt_rock": ["alternative rock", "alt rock"],
        "indie_rock": ["indie rock"],
        "classic_rock": ["classic rock", "rock classics"],
        "hard_rock": ["hard rock"],
        "punk": ["punk", "punk rock"],
        "pop_punk": ["pop punk"],
        "emo": ["emo", "emo rock", "post hardcore"],

        # METAL
        "metal": ["metal", "heavy metal"],
        "metalcore": ["metalcore"],
        "death_metal": ["death metal"],
        "black_metal": ["black metal"],
        "prog_metal": ["progressive metal", "prog metal"],

        # HIP-HOP ecosystem
        "hiphop": ["hip hop", "hip-hop", "rap"],
        "trap": ["trap"],
        "drill": ["drill", "uk drill", "ny drill"],
        "boom_bap": ["boom bap", "boombap"],
        "phonk": ["phonk", "drift phonk"],
        "grime": ["grime", "uk grime"],

        # R&B / SOUL
        "rnb": ["r&b", "rnb", "contemporary r&b"],
        "neo_soul": ["neo soul", "neosoul", "alternative r&b"],
        "soul": ["soul"],

        # ELECTRONIC / DANCE
        "electronic": ["edm", "electronic", "dance music"],
        "house": ["house", "deep house", "afro house", "tech house"],
        "techno": ["techno", "melodic techno", "peak time techno"],
        "trance": ["trance", "progressive trance"],
        "dnb": ["drum and bass", "dnb", "liquid dnb"],
        "dubstep": ["dubstep", "melodic dubstep"],
        "future_bass": ["future bass"],
        "synthwave": ["synthwave", "retrowave", "outrun"],
        "vaporwave": ["vaporwave"],
        "jersey_club": ["jersey club"],

        # CHILL / STUDY / BACKGROUND
        "lofi": ["lofi", "lo-fi", "lofi hip hop", "study beats", "chill beats"],
        "ambient": ["ambient", "dark ambient", "atmospheric"],
        "chillout": ["chillout", "downtempo"],

        # JAZZ / BLUES / FUNK / DISCO
        "jazz": ["jazz", "smooth jazz", "jazz standards", "modern jazz"],
        "blues": ["blues", "blues rock"],
        "funk": ["funk", "modern funk"],
        "disco": ["disco", "nu disco"],

        # CLASSICAL / SOUNDTRACK
        "classical": ["classical", "orchestra", "symphony", "piano concerto"],
        "soundtrack": ["soundtrack", "ost", "original soundtrack", "score"],

        # COUNTRY / FOLK
        "country": ["country", "country hits"],
        "alt_country": ["alt country", "americana"],
        "folk": ["folk", "singer songwriter", "singer-songwriter"],
        "bluegrass": ["bluegrass"],

        # GLOBAL: Africa / Caribbean
        "afrobeats": ["afrobeats", "afrobeat", "afropop"],
        "amapiano": ["amapiano", "log drum"],
        "dancehall": ["dancehall"],
        "reggae": ["reggae"],
        "ska": ["ska"],

        # GLOBAL: Latin
        "latin": ["latin", "latin pop"],
        "reggaeton": ["reggaeton", "perreo"],
        "bachata": ["bachata"],
        "salsa": ["salsa"],
        "regional_mexican": ["regional mexican", "música mexicana", "musica mexicana"],
        "corridos": ["corridos", "corridos tumbados"],
        "brazilian_funk": ["baile funk", "funk brasileiro"],

        # ASIA
        "kpop": ["kpop", "k-pop", "comeback"],
        "jpop": ["jpop", "j-pop"],
        "cpop": ["cpop", "mandopop", "c-pop"],

        # SOUTH ASIA
        "bollywood": ["bollywood", "hindi song", "hindi songs"],
        "punjabi": ["punjabi song", "punjabi songs"],
        "tamil": ["tamil song", "tamil songs", "kollywood"],
        "telugu": ["telugu song", "telugu songs", "tollywood"],

        # Catch-all
        "random": ["music", "new songs", "top songs", "trending songs"],
    }

    ARTIST_HINTS = {
        # POP
        "pop": [
            "taylor swift", "the weeknd", "dua lipa", "billie eilish", "olivia rodrigo",
            "sabrina carpenter", "ariana grande", "ed sheeran", "justin bieber", "adele",
            "harry styles", "post malone", "doja cat", "lady gaga", "bruno mars",
            "miley cyrus", "selena gomez", "shawn mendes", "kylie minogue", "coldplay"
        ],
        "alt_pop": [
            "lana del rey", "halsey", "troye sivan", "lorde", "charli xcx",
            "the 1975", "sia", "glass animals", "tove lo", "marina"
        ],
        "hyperpop": [
            "100 gecs", "agnes", "sophie", "kim petras", "brakence"
        ],

        # ROCK
        "rock": [
            "foo fighters", "arctic monkeys", "muse", "the killers", "green day",
            "linkin park", "red hot chili peppers", "paramore", "imagine dragons",
            "queens of the stone age", "u2", "radiohead", "nirvana", "pearl jam"
        ],
        "punk": ["green day", "blink-182", "sum 41", "the offspring", "fall out boy"],
        "emo": ["my chemical romance", "paramore", "panic! at the disco", "bring me the horizon"],

        # METAL
        "metal": [
            "metallica", "slipknot", "iron maiden", "megadeth", "pantera",
            "korn", "disturbed", "system of a down", "rammstein"
        ],
        "metalcore": ["bring me the horizon", "architects", "parkway drive", "bad omens", "spiritbox"],
        "death_metal": ["cannibal corpse", "gojira", "lamb of god", "lorna shore"],
        "prog_metal": ["dream theater", "tool", "opeth", "periphery"],

        # HIP-HOP
        "hiphop": [
            "drake", "kendrick lamar", "j cole", "travis scott", "future",
            "21 savage", "metro boomin", "eminem", "kanye west", "nicki minaj",
            "cardi b", "megan thee stallion", "doja cat", "lil baby", "gunna"
        ],
        "drill": ["central cee", "headie one", "digga d", "pop smoke", "fivio foreign"],
        "phonk": ["kordhell", "playaphonk"],

        # R&B / SOUL
        "rnb": ["sza", "frank ocean", "brent faiyaz", "the weeknd", "summer walker", "giveon", "bryson tiller", "h.e.r."],
        "neo_soul": ["daniel caesar", "jhené aiko", "miguel", "alicia keys"],

        # EDM / ELECTRONIC
        "electronic": [
            "calvin harris", "david guetta", "tiesto", "martin garrix", "skrillex",
            "marshmello", "zedd", "diplo", "swedish house mafia", "fred again",
            "illenium", "the chainsmokers", "deadmau5", "pegga gou", "peggy gou"
        ],
        "house": ["fisher", "john summit", "disclosure", "duke dumont", "peggy gou"],
        "techno": ["charlotte de witte", "amelie lens", "adam beyer"],
        "dnb": ["sub focus", "dimension", "andy c"],

        # COUNTRY / FOLK
        "country": [
            "morgan wallen", "luke combs", "zach bryan", "chris stapleton", "carrie underwood",
            "kacey musgraves", "lainey wilson", "jelly roll"
        ],
        "folk": ["noah kahan", "bon iver", "mumford & sons", "phoebe bridgers"],

        # AFROBEATS / AMAPIANO
        "afrobeats": ["burna boy", "wizkid", "davido", "rema", "tems", "asake", "ayra starr", "omah lay", "tyla"],
        "amapiano": ["kabza de small", "dj maphorisa", "major league djz", "focalistic", "sha sha"],

        # LATIN / REGGAETON / MEXICAN
        "reggaeton": ["bad bunny", "karol g", "rauw alejandro", "feid", "j balvin", "anuel", "ozuna", "daddy yankee"],
        "latin": ["shakira", "rosalía", "maluma", "becky g"],
        "corridos": ["peso pluma", "natanael cano", "fuerza regida", "junior h"],

        # K-POP / J-POP / ANIME-ish (you can keep anime separate too)
        "kpop": [
            "bts", "blackpink", "twice", "stray kids", "newjeans", "aespa", "itzy",
            "txt", "enhypen", "ive", "nct", "exo", "red velvet", "seventeen",
            "le sserafim", "(g)i-dle", "babymonster"
        ],
        "jpop": ["yoasobi", "ado", "kenshi yonezu", "eve", "lisa", "king gnu", "radwimps", "aimyon"],
        "anime": ["aniplex", "crunchyroll", "opening", "ending", "op", "ed"],

        # SOUTH ASIA
        "bollywood": [
            "arijit singh", "shreya ghoshal", "neha kakkar", "jubin nautiyal",
            "atif aslam", "a r rahman", "pritam", "vishal shekhar", "t-series",
            "zee music", "sony music india", "tips official"
        ],
        "punjabi": [
            "diljit dosanjh", "karan aujla", "ap dhillon", "sidhu moosewala",
            "shubh", "guru randhawa", "b praak", "jass manak",
            "speed records", "geet mp3"
        ],
        "tamil": ["anirudh", "a r rahman", "yuvan", "gv prakash", "sid sriram"],
        "telugu": ["thaman", "devi sri prasad", "sid sriram"],
    }

    STYLE_KEYWORDS = {
        "sped_up": ["sped up", "speed up", "nightcore"],
        "slowed_reverb": ["slowed", "slowed + reverb", "slowed reverb"],
        "remix": ["remix", "edit", "bootleg"],
        "acoustic": ["acoustic", "stripped", "unplugged"],
        "live": ["live", "concert", "festival"],
    }

    BLOCKED_PATTERNS = [
        # Learning / speaking content
        r"\b(tutorial|lesson|course|learn|learning)\b",
        r"\b(podcast|interview|talk|speech|lecture)\b",
        
        # “Content about content”
        r"\b(review|unboxing|reaction|gameplay)\b",
        
        # Long-form non-track uploads
        r"\b(full (movie|album|episode)|documentary)\b",
        
        # How-to / vlog formats
        r"\bhow to\b|\bguide\b|\btips\b|\btricks\b|\bvlog\b",
        
        # Non-music intent
        r"\b(practice|exercise|workout|meditation|asmr|audiobook|story)\b",
        
        # Playlists/compilations
        r"\b(compilation|playlist)\b",
        
        # Block "mix" as a standalone word, but NOT "remix"
        r"(?<!re)\bmix\b",
    ]

    LANGUAGE_HINTS = {
        "hindi": ["hindi", "bollywood", "arijit", "shreya", "jubin", "t-series", "zee music", "tips official"],
        "punjabi": ["punjabi", "diljit", "karan", "ap dhillon", "sidhu"],
        "korean": ["korean", "kpop", "k-pop", "hybe", "jyp", "sm entertainment"],
        "japanese": ["japanese", "jpop", "j-pop", "anime"],
        "spanish": ["spanish", "latino", "reggaeton", "bad bunny", "karol g"],
        "portuguese": ["portuguese", "brasil", "brazil", "anitta", "baile funk"],
        "french": ["french", "français", "francais"],
        "arabic": ["arabic", "arrabi", "amr diab"],
        "english": ["vevo", "official video", "official music video"],
    }

    def _build_genre_keywords(self):
        """Build genre keywords dynamically based on current year."""
        year = datetime.now().year
        
        # Modern suffixes
        suffixes = [
            "official video", "official music video", "official mv", "official audio",
            f"new songs {year}", f"hits {year}", "songs", "music video", "visualizer"
        ]
        
        out = {}
        for genre, terms in self.GENRE_TERMS.items():
            queries = []
            for t in terms:
                for s in suffixes:
                    queries.append(f"{t} {s}")
            # dedupe while keeping order
            seen = set()
            clean = []
            for q in queries:
                q2 = q.lower().strip()
                if q2 not in seen:
                    seen.add(q2)
                    clean.append(q2)
            out[genre] = clean[:30] # Max 30 per genre
            
        self.GENRE_KEYWORDS = out

    def _norm(self, s: str) -> str:
        s = s.lower()
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _contains_any(self, text: str, phrases: list[str]) -> int:
        """Count how many phrases appear in text."""
        c = 0
        for p in phrases:
            if p and p in text:
                c += 1
        return c

    def _detect_genre(self, track: Track) -> tuple[str | None, str | None, str | None]:
        """Detect genre, artist, and language using weighted scoring."""
        if not track:
            return None, None, None
            
        title = getattr(track, 'title', '')
        channel_name = getattr(track, 'channel_name', '')
        
        # Normalize text for matching
        text = self._norm(" ".join([title or "", channel_name or ""]))
        
        artist = None
        genre = None
        language = None

        # PRIORITY 1: Extract artist from title (Structure: "Artist - Title")
        if title and ('-' in title or '|' in title):
            parts = title.replace('|', '-').split('-')
            if len(parts) >= 2:
                first_part = parts[0].strip()
                second_part = parts[1].strip()
                # Common patterns
                if 2 < len(first_part) < 30:
                    keywords = ['official', 'video', 'lyrics', 'audio', 'music']
                    if not any(word in first_part.lower() for word in keywords):
                        artist = first_part
                elif 2 < len(second_part) < 30:
                    keywords = ['official', 'video', 'lyrics', 'audio', 'music']
                    if not any(word in second_part.lower() for word in keywords):
                        artist = second_part
        
        # Detect language first (using Hints)
        for lang, hints in self.LANGUAGE_HINTS.items():
            if any(hint in text for hint in hints):
                 language = lang
                 break
        
        # Weighted Scoring for Genre
        scores = {g: 0 for g in self.GENRE_TERMS.keys()}
        
        # 1. Genre Term Hits (+2)
        for g, terms in self.GENRE_TERMS.items():
            scores[g] += 2 * self._contains_any(text, [self._norm(x) for x in terms])
            
        # 2. Artist Hint Hits (+4) - Strong signal
        found_artist_hint = False
        for g, artists in self.ARTIST_HINTS.items():
             if g in scores:
                 # Check for artist matches
                 matched_artists = [a for a in artists if self._norm(a) in text]
                 if matched_artists:
                     scores[g] += 4 * len(matched_artists)
                     # Determine artist from hint if not found yet
                     if not artist:
                         # Use the longest matched artist as likely candidate
                         artist = max(matched_artists, key=len)
                         found_artist_hint = True
        
        # 3. Official Video Boost (+1) - Mild boost if authentic
        if any(k in text for k in ["official video", "official music video", "official mv", "vevo"]):
            for g in scores:
                if scores[g] > 0: # Only boost already suspected genres
                    scores[g] += 1
                    
        # Find best genre
        best_genre = max(scores, key=scores.get)
        if scores[best_genre] > 0:
            genre = best_genre
        else:
            # Fallback heuristics
            if "rap" in text or "hip hop" in text: genre = "hiphop"
            elif "edm" in text or "house" in text: genre = "electronic"
            elif "rnb" in text or "r&b" in text: genre = "rnb"
            elif "hindi" in text or "bollywood" in text: genre = "bollywood"
            elif "punjabi" in text: genre = "punjabi"
            
        # PRIORITY 2: Extract artist from channel (Fallback)
        if not artist and track.channel_name:
            clean_channel = track.channel_name.replace(" - Topic", "").replace("VEVO", "").replace(" Official", "").strip()
            generic_names = ["music", "records", "entertainment", "channel", "label", "productions"]
            if not any(g in clean_channel.lower() for g in generic_names):
                artist = clean_channel
                
        return genre, artist, language

    def _generate_dynamic_keyword(self, genre: str | None, artist: str | None, language: str | None = None, previous_title: str = None, attempt: int = 0) -> str:
        """Generate a dynamic search keyword based on detected genre/artist/language."""
        import random
        
        # STRATEGY 1: Artist-based search (PRIMARY)
        if artist and len(artist) > 3:
            generic_names = {"vevo", "official", "music", "records", "entertainment", "topic", "channel", "label"}
            if not any(g in artist.lower() for g in generic_names):
                if attempt == 0:
                    return f"{artist} songs"
                elif attempt == 1:
                    return f"{artist} latest songs"
                elif attempt == 2:
                    return f"songs like {artist}"
        
        # Language prefix
        lang_prefix = ""
        if language and language not in ("english", None):
            lang_prefix = f"{language} "
        
        # STRATEGY 2: Genre + Language
        if genre and genre in self.GENRE_KEYWORDS:
            keywords = self.GENRE_KEYWORDS[genre]
            idx = (attempt + random.randint(0, 2)) % len(keywords)
            return f"{lang_prefix}{keywords[idx]}"
            
        # STRATEGY 3: Language-only fallback
        year = getattr(self, 'YEAR', datetime.now().year)
        if language and language != "english":
            queries = [
                f"{language} songs {year}", 
                f"best {language} music", 
                f"popular {language} songs", 
                f"new {language} hits"
            ]
            return queries[attempt % len(queries)]
        
        # STRATEGY 4: Ultimate fallback
        fallback_queries = [
            f"popular songs {year}",
            "top music hits", 
            "best songs playlist",
            f"trending music {year}",
            "new songs official"
        ]
        return fallback_queries[(attempt + random.randint(0, 2)) % len(fallback_queries)]

    def _is_similar_title(self, title1: str, title2: str) -> bool:
        """Check if two titles are too similar (potential duplicate).
        
        Normalizes titles by removing common suffixes like 'Official Video', 'Lyric Video', etc.
        to catch same song in different versions.
        """
        if not title1 or not title2:
            return False
        
        # Normalize function to remove common video type suffixes
        def normalize_title(title):
            t = title.lower().strip()
            # Remove common suffixes that indicate song versions
            suffixes_to_remove = [
                '(official video)', '(official music video)', '(official audio)',
                '(lyric video)', '(lyrics)', '(lyrics video)', '(official lyric video)',
                '(audio)', '(official)', '(music video)', '(visualizer)',
                '(video)', '[official video]', '[official audio]', '[lyric video]',
                '[lyrics]', '- official video', '- official audio', '- lyric video',
                '| official video', '| official audio', 'official video', 'official audio',
                'lyric video', 'lyrics video', 'music video', 'full video',
                '(original)', '(original version)', '(extended version)', '(radio edit)',
                '(clean version)', '(explicit)', '(remastered)', '(remix)',
                '(slowed + reverb)', '(slowed)', '(sped up)', '(nightcore)',
                'ft.', 'feat.', 'featuring'
            ]
            
            for suffix in suffixes_to_remove:
                t = t.replace(suffix, '')
            
            # Remove extra whitespace and punctuation
            t = ' '.join(t.split())  # Normalize whitespace
            t = t.strip('- |[]().')
            
            return t
        
        t1 = normalize_title(title1)
        t2 = normalize_title(title2)
        
        # Exact match after normalization
        if t1 == t2:
            return True
        
        # One contains the other (after normalization)
        if len(t1) > 5 and len(t2) > 5:  # Avoid false positives with very short titles
            if t1 in t2 or t2 in t1:
                return True
        
        # Check word overlap (if >80% words match, consider similar)
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        # Remove common words that don't indicate uniqueness
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words1 = words1 - common_words
        words2 = words2 - common_words
        
        if len(words1) > 0 and len(words2) > 0:
            overlap = len(words1 & words2)
            min_len = min(len(words1), len(words2))
            if min_len > 0 and overlap / min_len > 0.8:  # 80% overlap = duplicate
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
        # Blocked keywords using regex patterns
        if any(re.search(pat, title, re.IGNORECASE) for pat in self.BLOCKED_PATTERNS):
            return False

        # Duplicate check
        if previous_title and self._is_similar_title(title, previous_title):
            return False
        
        return True

    async def smart_autoplay(self, mode: str | bool, previous_track: Track = None) -> Track | None:
        """
        Smart Autoplay Logic - prioritizes continuity with previous track.
        
        Strategy:
        1. Try TF-IDF content-based recommendations (if enabled and previous track exists)
        2. Falls back to artist-based search
        3. Then genre-based search
        4. Only uses random genres as last resort
        
        mode: 'on' (or True), 'smart', or specific genre 'pop', 'rock', etc.
        """
        if mode == True or mode == "on":
            mode = "smart"
             
        genre = None
        artist = None
        language = None
        # Use full_title if available (stored from previous autoplay), otherwise use title
        previous_title = getattr(previous_track, 'full_title', None) or (previous_track.title if previous_track else None)
        
        # STRATEGY 0: TF-IDF Content-Based Recommendations (PRIMARY)
        if mode == "smart" and previous_track and self.recommender:
            try:
                logger.info(f"🎯 Trying TF-IDF recommendations for: '{previous_track.title}'")
                # Await the async get_recommendations method
                recommendations = await self.recommender.get_recommendations(
                    previous_track.title, 
                    limit=config.RECOMMENDATION_LIMIT
                )
                
                if recommendations:
                    logger.info(f"✅ Found {len(recommendations)} TF-IDF recommendations")
                    
                    # Try to find these recommended tracks on YouTube
                    # Try top 5 recommendations to increase chance of finding valid tracks
                    for i, rec_title in enumerate(recommendations[:5]):
                        try:
                            logger.info(f"Searching for recommended track {i+1}: '{rec_title}'")
                            
                            # Search for this recommended track
                            with proxy_env():
                                _search = VideosSearch(rec_title, limit=3, with_live=False)
                                results = await _search.next()
                            
                            if results and results["result"]:
                                # Try to find exact or close match
                                for res in results["result"]:
                                    if self._is_good_track(res, previous_title):
                                        data = res
                                        full_title = data.get('title')
                                        logger.info(f"🎵 TF-IDF Recommendation SUCCESS: '{full_title}'")
                                        
                                        track = Track(
                                            id=data.get("id"),
                                            channel_name=data.get("channel", {}).get("name"),
                                            duration=data.get("duration"),
                                            duration_sec=utils.to_seconds(data.get("duration")),
                                            title=full_title[:25],
                                            thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                                            url=data.get("link"),
                                            view_count=data.get("viewCount", {}).get("short"),
                                            video=previous_track.video if previous_track else False,
                                            req_type="search"
                                        )
                                        track.full_title = full_title
                                        return track
                        except Exception as e:
                            logger.debug(f"Failed to search for recommendation '{rec_title}': {e}")
                            continue
                    
                    logger.info("TF-IDF recommendations found but couldn't find valid YouTube tracks, falling back...")
                else:
                    logger.info("No TF-IDF recommendations found, falling back to genre detection...")
                    
            except Exception as e:
                logger.warning(f"TF-IDF recommendation failed: {e}")
                # Continue to fallback strategies
        
        # STRATEGY 1: Determine Genre/Artist/Language from previous track (for fallback)
        if mode == "smart" and previous_track:
            genre, artist, language = self._detect_genre(previous_track)
            logger.info(f"Smart Autoplay Fallback: Detected genre={genre}, artist={artist}, language={language}")
        elif mode in self.GENRE_KEYWORDS:
            # User explicitly requested a genre
            genre = mode
            # Don't use previous track info for explicit genre mode
            previous_title = None
            artist = None
        
        # STRATEGY 2: Search with progressive fallback strategy
        for attempt in range(3):
            try:
                # Generate keyword with attempt number for progressive fallback
                keyword = self._generate_dynamic_keyword(genre, artist, language, previous_title, attempt)
                logger.info(f"Smart Autoplay (attempt {attempt + 1}): Searching '{keyword}'")
                
                with proxy_env():
                    _search = VideosSearch(keyword, limit=15, with_live=False)
                    results = await _search.next()
                    
                filtered = []
                if results and results["result"]:
                    for res in results["result"]:
                        if self._is_good_track(res, previous_title):
                            filtered.append(res)
            except Exception as search_err:
                logger.error(f"Search failed for '{keyword}': {search_err}")
                # Continue to next attempt
                continue
            
            if filtered:
                # Pick from top 5 results (more relevant) instead of all
                top_results = filtered[:5]
                import random
                data = random.choice(top_results)
                
                full_title = data.get("title")
                logger.info(f"Smart Autoplay: Selected '{full_title}' from {len(filtered)} filtered results")
                
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name"),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=full_title[:25],  # Display truncated
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    video=previous_track.video if previous_track else False,
                    req_type="search"
                )
                # Store full title for future duplicate checking
                track.full_title = full_title
                return track
            
            logger.warning(f"Smart Autoplay: No results for '{keyword}', trying next strategy...")

        logger.error("Smart Autoplay: All attempts failed, no track found")
        return None

    # Keep old method for backward compat or fallback
    async def autoplay_search(self, query: str, video: bool = False) -> Track | None:
        # Search for the same title but get a few results
        # We'll pick the 2nd result to pretend it's "next"
        # Ideally we'd use related videos but this is a decent heuristic for now
        
        with proxy_env():
             _search = VideosSearch(query, limit=5, with_live=False)
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
