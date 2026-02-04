# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types
from bot import app, anon as calls, db, logger, queue
from bot.helpers import admin_check, utils

@app.on_message(filters.command("audio") & filters.group)
@admin_check
async def change_audio_stream(client, message, **kwargs):
    chat_id = message.chat.id
    
    if not await db.get_call(chat_id):
        return await message.reply_text("❌ No active playback.")
        
    try:
        # Check command args for index
        # Usage: /audio 2 (for audio track 2)
        if len(message.command) < 2:
            return await message.reply_text(
                "ℹ️ **Audio Stream Switcher**\n\n"
                "Usage: `/audio [track_index]`\n"
                "Example: `/audio 1` (Default), `/audio 2` (Hindi/Alt)\n\n"
                "Try different numbers if the audio doesn't change."
            )
            
        try:
            # 0-indexed internally, but user uses 1-indexed
            # If user sends 1 -> index 0
            # If user sends 2 -> index 1
            index = int(message.command[1]) - 1
        except ValueError:
            return await message.reply_text("❌ Please enter a valid number.")
            
        if index < 0:
            return await message.reply_text("❌ valid index starts from 1.")
        
        # Check if current media has audio streams
        media = await queue.get_current(chat_id)
        if not media:
            return await message.reply_text("❌ No media currently playing.")
        
        # Verify media has audio streams
        audio_streams = getattr(media, 'audio_streams', [])
        if not audio_streams or len(audio_streams) <= 1:
            return await message.reply_text(
                "❌ **No multiple audio tracks available**\n\n"
                "This video either has:\n"
                "• Only one audio track\n"
                "• No audio streams detected\n"
                "• Is streaming from HTTP (audio detection only works for downloaded files)"
            )
        
        # Check if requested index exists
        if index >= len(audio_streams):
            return await message.reply_text(
                f"❌ **Track {index + 1} doesn't exist**\n\n"
                f"This video has only {len(audio_streams)} audio track(s).\n"
                f"Available: 1 to {len(audio_streams)}"
            )
            
        status = await message.reply_text(f"🔄 **Switching audio stream to Track {index + 1}...**\n\n_Playback will restart at current position._")
        
        success = await calls.change_stream(chat_id, audio_index=index)
        
        if success:
             await status.edit_text(f"✅ **Switched to Audio Track {index + 1}**")
        else:
             await status.edit_text("❌ Failed to switch stream.")
             
    except Exception as e:
        logger.error(f"Error in /audio command: {e}")
        await message.reply_text("❌ An error occurred.")
