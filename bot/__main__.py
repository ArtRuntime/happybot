# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import asyncio
import importlib
from pyrogram import idle
from bot import (anon, app, config, db,
                   logger, stop, userbot, yt)
from bot.plugins import all_modules
import socket
import dns.resolver



import subprocess
import time
import os

async def main():
    if config.PROXY_URL:
        # Log Proxy Config (Masked)
        masked_proxy = f"{config.PROXY_SCHEME}://{config.PROXY_HOST}:{config.PROXY_PORT}"
        if config.PROXY_USERNAME:
            masked_proxy = f"{config.PROXY_SCHEME}://{config.PROXY_USERNAME}:***@{config.PROXY_HOST}:{config.PROXY_PORT}"
        logger.info(f"Proxy Configured: {masked_proxy}")
    else:
        logger.info("No Proxy Configured. Running Direct.")

    await db.connect()
    await app.boot()
    await userbot.boot()
    await anon.boot()

    for module in all_modules:
        importlib.import_module(f"bot.plugins.{module}")
    logger.info(f"Loaded {len(all_modules)} modules.")

    if config.COOKIES_URL:
        await yt.save_cookies(config.COOKIES_URL)
        
        # Start background cookie refresh task
        async def cookie_refresh_loop():
            while True:
                await asyncio.sleep(config.COOKIE_REFRESH_INTERVAL)
                logger.info("Refreshing cookies from COOKIES_URL...")
                await yt.save_cookies(config.COOKIES_URL)
        
        asyncio.create_task(cookie_refresh_loop())

    sudoers = await db.get_sudoers()
    app.sudoers.update(sudoers)
    app.bl_users.update(await db.get_blacklisted())
    logger.info(f"Loaded {len(app.sudoers)} sudo users.")

    await idle()
    await stop()


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        pass
