# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types
from pyrogram.errors import MessageIdInvalid

from bot import anime, app, db, lang, logger
from bot.helpers import buttons


# Store anime data with short indices (to avoid Telegram's 64-byte callback_data limit)
# Format: {chat_id: {"search": [results], "anime": {idx: anime_id}, "episodes": {anime_id: episodes}}}
anime_cache = {}


def get_cache(chat_id: int):
    """Get or create cache for a chat."""
    if chat_id not in anime_cache:
        anime_cache[chat_id] = {"search": [], "anime": {}, "episodes": {}}
    return anime_cache[chat_id]


def cache_search_results(chat_id: int, results: list) -> dict:
    """Cache search results and return anime_id -> index mapping."""
    cache = get_cache(chat_id)
    cache["search"] = results
    cache["anime"] = {str(i): r.get("id", "") for i, r in enumerate(results)}
    return cache["anime"]


@app.on_message(filters.command(["anime"]) & filters.group & ~app.bl_users)
@lang.language()
async def anime_command(_, message: types.Message):
    """Search and stream anime."""
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/anime <anime name>`\n\n"
            "**Example:** `/anime naruto`"
        )
    
    query = " ".join(message.command[1:])
    msg = await message.reply_text(f"🔍 Searching for **{query}**...")
    
    try:
        results = await anime.search_anime(query)
        
        if not results or len(results) == 0:
            return await msg.edit_text(
                f"❌ No anime found for **{query}**.\n"
                "Try a different search term."
            )
        
        # Cache results with short indices
        cache_search_results(message.chat.id, results)
        
        # Show search results with pagination
        keyboard = buttons.anime_search_results(results, message.chat.id, page=0)
        
        await msg.edit_text(
            f"🔍 **Search Results for:** {query}\n\n"
            f"Found {len(results)} anime(s). Select one:",
            reply_markup=keyboard
        )
        
        # Delete command message
        try:
            await message.delete()
        except:
            pass
            
    except Exception as e:
        logger.error(f"Anime search error: {e}", exc_info=True)
        await msg.edit_text("❌ An error occurred while searching.")
