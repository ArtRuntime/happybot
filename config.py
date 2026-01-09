from os import getenv
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.API_ID = int(getenv("API_ID", 0))
        self.API_HASH = getenv("API_HASH")

        self.BOT_TOKEN = getenv("BOT_TOKEN")
        self.MONGO_URL = getenv("MONGO_URL")

        self.LOGGER_ID = int(getenv("LOGGER_ID", 0))
        self.OWNER_ID = int(getenv("OWNER_ID", 0))

        self.DURATION_LIMIT = int(getenv("DURATION_LIMIT", 60)) * 60
        self.QUEUE_LIMIT = int(getenv("QUEUE_LIMIT", 20))
        self.PLAYLIST_LIMIT = int(getenv("PLAYLIST_LIMIT", 20))

        self.SESSION1 = getenv("SESSION", None)
        self.SESSION2 = getenv("SESSION2", None)
        self.SESSION3 = getenv("SESSION3", None)

        self.SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/alex5402")
        self.SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/alex5402")

        self.AUTO_END: bool = getenv("AUTO_END", False)
        self.AUTO_LEAVE: bool = getenv("AUTO_LEAVE", False)
        self.VIDEO_PLAY: bool = getenv("VIDEO_PLAY", True)
        self.COOKIES_URL = [
            url for url in getenv("COOKIES_URL", "").split(" ")
            if url and "batbin.me" in url
        ]
        self.DEFAULT_THUMB = getenv("DEFAULT_THUMB", "https://te.legra.ph/file/3e40a408286d4eda24191.jpg")
        self.PING_IMG = getenv("PING_IMG", "https://files.catbox.moe/haagg2.png")
        self.START_IMG = getenv("START_IMG", "https://files.catbox.moe/zvziwk.jpg")
        
        # Proxy Configuration
        self.PROXY_HOST = getenv("PROXY_HOST")
        self.PROXY_PORT = int(getenv("PROXY_PORT", 0))
        self.PROXY_HTTP_PORT = int(getenv("PROXY_HTTP_PORT", 0)) # Fallback/Alternative HTTP port
        self.PROXY_USERNAME = getenv("PROXY_USERNAME")
        self.PROXY_PASSWORD = getenv("PROXY_PASSWORD")
        self.PROXY_SCHEME = getenv("PROXY_SCHEME", "socks5") # "socks5" or "http"
        
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
            for var in ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL", "LOGGER_ID", "OWNER_ID", "SESSION1"]
            if not getattr(self, var)
        ]
        if missing:
            raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
