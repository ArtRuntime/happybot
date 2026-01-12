# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from ytmusicapi import YTMusic
from pyrogram import types
import asyncio

from bot import app
from bot.helpers import buttons, utils

# Initialize YTMusic
ytmusic = YTMusic()

@app.on_inline_query(~app.bl_users)
async def inline_query_handler(_, query: types.InlineQuery):
    text = query.query.strip().lower()
    if not text:
        return

    try:
        # Search using ytmusicapi
        results = await asyncio.to_thread(ytmusic.search, text, filter="songs", limit=15)
        
        answers = []
        for video in results:
            if video.get('resultType') not in ['song', 'video']:
                continue
                
            video_id = video.get("videoId")
            if not video_id:
                continue
                
            title = video.get("title", "Unknown Title")
            
            # Extract artist
            artists = video.get("artists", [])
            channel = artists[0].get("name") if artists else "Unknown Artist"
            
            # Duration
            duration = video.get("duration", "N/A")
            
            # Thumbnail
            thumbnails = video.get("thumbnails", [])
            thumbnail = thumbnails[-1].get("url", "").split("?")[0] if thumbnails else ""
            
            link = f"https://www.youtube.com/watch?v={video_id}"
            
            description = f"{channel} | {duration}"
            caption = (
                f"<b>Title:</b> <a href='{link}'>{title[:100]}</a>\n\n"
                f"<b>Artist:</b> {channel}\n"
                f"<b>Duration:</b> {duration}\n\n"
                f"<u><i>Fetched by {app.name}</i></u>"
            )

            answers.append(
                types.InlineQueryResultPhoto(
                    photo_url=thumbnail,
                    title=title,
                    description=description,
                    caption=caption,
                    reply_markup=buttons.yt_key(link),
                )
            )

        if answers:
            await app.answer_inline_query(query.id, results=answers, cache_time=5)
    except Exception as e:
        print(f"Inline query error: {e}")
