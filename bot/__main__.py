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

# --- Monkeypatch for PyTgCalls Compatibility ---
# py-tgcalls expects UpdateGroupCall to have .chat.id, but kurigram's Raw UpdateGroupCall 
# only has .peer (PeerChannel/PeerChat). We add a proxy .chat property.
try:
    from pyrogram.raw.types import UpdateGroupCall
    
    class MockChat:
        def __init__(self, peer):
            self._peer = peer
        
        @property
        def id(self):
            if hasattr(self._peer, "channel_id"):
                return self._peer.channel_id
            if hasattr(self._peer, "chat_id"):
                return self._peer.chat_id
            return 0

    if not hasattr(UpdateGroupCall, "chat"):
        logger.info("Applying UpdateGroupCall monkeypatch for PyTgCalls...")
        setattr(UpdateGroupCall, "chat", property(lambda self: MockChat(self.peer)))
    
    # Fix for 'UpdateGroupCall' object has no attribute 'chat_id'
    if not hasattr(UpdateGroupCall, "chat_id"):
        setattr(UpdateGroupCall, "chat_id", property(lambda self: self.chat.id))
        
except ImportError:
    pass
except Exception as e:
    logger.error(f"Failed to apply monkeypatch: {e}")

def force_google_dns():
    """Force usage of Google DNS to resolve music.youtube.com issues."""
    try:
        logger.info("Forcing Google DNS (8.8.8.8)...")
        dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
        dns.resolver.default_resolver.nameservers = ["8.8.8.8", "8.8.4.4"]
        
        # Patch socket.getaddrinfo to use dnspython
        original_getaddrinfo = socket.getaddrinfo
        
        def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            try:
                # Use custom resolver for specific domains or all
                answers = dns.resolver.resolve(host, 'A')
                ip = answers[0].to_text()
                # logger.debug(f"Resolved {host} -> {ip}")
                return original_getaddrinfo(ip, port, family, type, proto, flags)
            except Exception:
                # Fallback to system DNS
                return original_getaddrinfo(host, port, family, type, proto, flags)
                
        socket.getaddrinfo = patched_getaddrinfo
        logger.info("DNS patching applied.")
    except Exception as e:
        logger.error(f"Failed to force DNS: {e}")
# -----------------------------------------------

async def main():
    # Force DNS first
    force_google_dns()

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
    
    # Invite all assistants to logs group after bot is fully ready
    await userbot.invite_assistants_to_logs()

    if config.COOKIES_URL or config.BROWSER_JSON_URL:
        # Initial fetch
        await yt.save_cookies(config.COOKIES_URL)
        
        # Start background cookie refresh task
        async def cookie_refresh_loop():
            while True:
                await asyncio.sleep(config.COOKIE_REFRESH_INTERVAL)
                logger.info("Auto-refreshing cookies/auth...")
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
