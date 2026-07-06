# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
from pyrogram import filters, types
from bot import app, db, lang


@app.on_message(filters.command(["setcache"]) & app.sudoers)
@lang.language()
async def _setcache(_, m: types.Message):
    if len(m.command) < 2:
        return await m.reply_text("❌ <b>Usage:</b> <code>/setcache <limit></code>\n\nExample: <code>/setcache 10GB</code>, <code>/setcache 500MB</code>")
        
    limit_str = m.text.split(None, 1)[1]
    try:
        limit_bytes = await db.set_max_cache_limit(limit_str)
        # Fetch formatted limit string
        _, formatted_str = await db.get_max_cache_limit()
        await m.reply_text(f"✅ <b>Max cache limit updated to:</b> <code>{formatted_str}</code> ({limit_bytes:,} bytes).")
    except ValueError as e:
        await m.reply_text(f"❌ <b>Error:</b> {e}")
    except Exception as e:
        await m.reply_text(f"❌ <b>Failed to set limit:</b> {e}")


@app.on_message(filters.command(["cacheinfo"]) & app.sudoers)
@lang.language()
async def _cacheinfo(_, m: types.Message):
    sent = await m.reply_text("📊 Gathering cache statistics...")
    
    try:
        limit_bytes, limit_str = await db.get_max_cache_limit()
        
        # Calculate current cache size from database
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$file_size"}}}]
        cursor = await db.cache_metadata.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        total_bytes = result[0]["total"] if result else 0
        
        # Format current size
        if total_bytes >= 1024 * 1024 * 1024 * 1024:
            current_str = f"{total_bytes / (1024 * 1024 * 1024 * 1024):.2f} TB"
        elif total_bytes >= 1024 * 1024 * 1024:
            current_str = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"
        elif total_bytes >= 1024 * 1024:
            current_str = f"{total_bytes / (1024 * 1024):.2f} MB"
        elif total_bytes >= 1024:
            current_str = f"{total_bytes / 1024:.2f} KB"
        else:
            current_str = f"{total_bytes} B"
            
        total_songs = await db.cache_metadata.count_documents({})
        
        # Get top 5 most played songs
        top_songs = []
        async for song in db.cache_metadata.find().sort("play_count", -1).limit(5):
            top_songs.append(f"• <code>{song.get('title', 'Unknown')[:30]}</code> (Played: {song.get('play_count', 0)})")
            
        top_played_str = "\n".join(top_songs) if top_songs else "None yet"
        
        txt = (
            f"📁 <b>Cache Directory Info:</b>\n\n"
            f"• <b>Current Size:</b> <code>{current_str}</code>\n"
            f"• <b>Max Limit:</b> <code>{limit_str}</code>\n"
            f"• <b>Total Cached Songs:</b> <code>{total_songs}</code>\n\n"
            f"🔥 <b>Top 5 Most Played Cached Songs:</b>\n"
            f"{top_played_str}"
        )
        await sent.edit_text(txt)
    except Exception as e:
        await sent.edit_text(f"❌ <b>Error gathering info:</b> {e}")
