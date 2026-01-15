from os import getenv
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.API_ID = int(getenv("API_ID", 0))
        self.API_HASH = getenv("API_HASH")

        self.BOT_TOKEN = getenv("BOT_TOKEN")
        self.MONGO_URL = getenv("MONGO_URL")
        self.MONGO_DB_NAME = getenv("MONGO_DB_NAME", "HappyBot")
        self.REDIS_URL = getenv("REDIS_URL")
        self.REDIS_PREFIX = getenv("REDIS_PREFIX", "happybot-")

        self.LOGGER_ID = int(getenv("LOGGER_ID", 0))
        self.OWNER_ID = int(getenv("OWNER_ID", 0))

        self.DURATION_LIMIT = int(getenv("DURATION_LIMIT", 60)) * 60
        self.QUEUE_LIMIT = int(getenv("QUEUE_LIMIT", 20))
        self.PLAYLIST_LIMIT = int(getenv("PLAYLIST_LIMIT", 20))

        # Sessions (optional - now stored in MongoDB)
        self.SESSION1 = getenv("SESSION", None) or getenv("SESSION1", None)
        self.SESSION2 = getenv("SESSION2", None)
        self.SESSION3 = getenv("SESSION3", None)

        self.SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/alex5402")
        self.SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/alex5402")

        self.AUTO_END: bool = getenv("AUTO_END", "false").lower() in ("true", "1", "yes")
        self.AUTO_LEAVE: bool = getenv("AUTO_LEAVE", "false").lower() in ("true", "1", "yes")
        self.VIDEO_PLAY: bool = getenv("VIDEO_PLAY", "true").lower() in ("true", "1", "yes")
        self.COOKIES_URL = [
            url for url in getenv("COOKIES_URL", "").split(" ")
            if url
        ]
        self.BROWSER_JSON_URL = getenv("BROWSER_JSON_URL")
        self.COOKIE_REFRESH_INTERVAL = int(getenv("COOKIE_REFRESH_INTERVAL", 5)) * 60  # Default 5 minutes
        self.DEFAULT_THUMB = getenv("DEFAULT_THUMB", "https://images.alphacoders.com/685/thumb-1920-685120.png")
        self.PING_IMG = getenv("PING_IMG", "https://images6.alphacoders.com/134/thumb-1920-1345576.jpeg")
        self.START_IMG = getenv("START_IMG", "https://images3.alphacoders.com/132/thumbbig-1323165.webp")
        self.AFK_TIMEOUT = int(getenv("AFK_TIMEOUT", 5)) * 60  # Default 5 minutes
        
        # Direct Streaming (stream from URL without downloading)
        self.ENABLE_DIRECT_STREAMING = getenv("ENABLE_DIRECT_STREAMING", "true").lower() in ("true", "1", "yes")
        self.STREAM_QUALITY = getenv("STREAM_QUALITY", "medium")  # low, medium, high
        
        # yt-dlp logging
        self.YTDLP_VERBOSE = getenv("YTDLP_VERBOSE", "false").lower() in ("true", "1", "yes")
        
        # Anime API
        self.ANIME_API_URL = getenv("ANIME_API_URL", "https://anime-api2-three.vercel.app")
        
        # Player Update Interval (seconds) - Default 7s zada jaldi krenge to rate limit laga jayega
        self.PLAYER_UPDATE_INTERVAL = int(getenv("PLAYER_UPDATE_INTERVAL", 7))
        
        # Proxy Configuration
        self.PROXY_HOST = getenv("PROXY_HOST", "127.0.0.1")
        self.PROXY_PORT = int(getenv("PROXY_PORT") or getenv("PROXY_HTTP_PORT") or 0)
        self.PROXY_HTTP_PORT = int(getenv("PROXY_HTTP_PORT", 0)) # Fallback/Alternative HTTP port
        self.PROXY_USERNAME = getenv("PROXY_USERNAME")
        self.PROXY_PASSWORD = getenv("PROXY_PASSWORD")
        self.PROXY_SCHEME = getenv("PROXY_SCHEME", "http") # "socks5" or "http"
        
        self.PROXY_DICT = None
        self.PROXY_URL = None
        
        if self.PROXY_HOST and self.PROXY_PORT:
            self.PROXY_DICT = {
                "scheme": self.PROXY_SCHEME,
                "hostname": self.PROXY_HOST,
                "port": self.PROXY_PORT,
            }
            if self.PROXY_USERNAME and self.PROXY_PASSWORD:
                self.PROXY_DICT["username"] = self.PROXY_USERNAME
                self.PROXY_DICT["password"] = self.PROXY_PASSWORD
                self.PROXY_URL = f"{self.PROXY_SCHEME}://{self.PROXY_USERNAME}:{self.PROXY_PASSWORD}@{self.PROXY_HOST}:{self.PROXY_PORT}"
            else:
                self.PROXY_URL = f"{self.PROXY_SCHEME}://{self.PROXY_HOST}:{self.PROXY_PORT}"

    def check(self):
        missing = [
            var
            for var in ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL", "LOGGER_ID", "OWNER_ID"]
            if not getattr(self, var)
        ]
        if missing:
            raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

