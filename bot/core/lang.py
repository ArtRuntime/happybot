# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import json
from functools import wraps
from pathlib import Path

from pyrogram import errors

from bot import db, logger


class Language:
    """
    Language class - English only.
    """

    def __init__(self):
        self.lang_dir = Path("bot/locales")
        self.english = self._load_english()

    def _load_english(self):
        lang_file = self.lang_dir / "en.json"
        with open(lang_file, "r", encoding="utf-8") as file:
            return json.load(file)

    async def get_lang(self, chat_id: int) -> dict:
        return self.english

    def get_languages(self) -> dict:
        return {"en": "English"}

    def language(self):
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                fallen = next(
                    (
                        arg
                        for arg in args
                        if hasattr(arg, "chat") or hasattr(arg, "message")
                    ),
                    None,
                )

                if not fallen.from_user:
                    return

                if hasattr(fallen, "chat"):
                    chat = fallen.chat
                elif hasattr(fallen, "message"):
                    chat = fallen.message.chat

                if chat.id in db.blacklisted_chats or chat.id in db.blacklisted_users:
                    logger.warning(f"Chat {chat.id} is blacklisted, leaving...")
                    return await chat.leave()

                setattr(fallen, "lang", self.english)
                try:
                    return await func(*args, **kwargs)
                except (errors.Forbidden, errors.exceptions.Forbidden):
                    logger.warning(f"Cannot write to chat {chat.id}, leaving...")
                    return await chat.leave()

            return wrapper

        return decorator
