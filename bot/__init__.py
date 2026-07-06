# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Patch httpx to support 'proxies' keyword argument for backward compatibility with youtube-search-python
import httpx

original_async_init = httpx.AsyncClient.__init__
def patched_async_init(self, *args, **kwargs):
    if "proxies" in kwargs:
        proxies = kwargs.pop("proxies")
        if proxies:
            if isinstance(proxies, dict):
                if "https://" in proxies:
                    kwargs["proxy"] = proxies["https://"]
                elif "http://" in proxies:
                    kwargs["proxy"] = proxies["http://"]
                else:
                    kwargs["proxy"] = list(proxies.values())[0]
            else:
                kwargs["proxy"] = proxies
    original_async_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = patched_async_init

original_init = httpx.Client.__init__
def patched_init(self, *args, **kwargs):
    if "proxies" in kwargs:
        proxies = kwargs.pop("proxies")
        if proxies:
            if isinstance(proxies, dict):
                if "https://" in proxies:
                    kwargs["proxy"] = proxies["https://"]
                elif "http://" in proxies:
                    kwargs["proxy"] = proxies["http://"]
                else:
                    kwargs["proxy"] = list(proxies.values())[0]
            else:
                kwargs["proxy"] = proxies
    original_init(self, *args, **kwargs)
httpx.Client.__init__ = patched_init


import time
import logging

logging.basicConfig(
    format="[%(asctime)s - %(levelname)s] - %(name)s: %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
    ],
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("ntgcalls").setLevel(logging.CRITICAL)
logging.getLogger("pymongo").setLevel(logging.ERROR)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pytgcalls").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


__version__ = "3.0.1"

from config import Config

config = Config()
config.check()
tasks = []
boot = time.time()

from bot.core.bot import Bot
app = Bot()

from bot.core.dir import ensure_dirs
ensure_dirs()

from bot.core.userbot import Userbot
userbot = Userbot()

from bot.core.mongo import MongoDB
db = MongoDB()

from bot.core.lang import Language
lang = Language()

from bot.core.telegram import Telegram
from bot.core.youtube import YouTube
tg = Telegram()
yt = YouTube()

from bot.helpers import Queue
queue = Queue()

from bot.core.calls import TgCall
anon = TgCall()


async def stop() -> None:
    logger.info("Stopping...")
    for task in tasks:
        task.cancel()
        try:
            await task
        except:
            pass

    await app.exit()
    await userbot.exit()
    await db.close()

    logger.info("Stopped.\n")
