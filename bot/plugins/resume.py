# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types
from pyrogram.types import InputMediaPhoto

from bot import anon, app, config, db, lang, queue
from bot.helpers import buttons, can_manage_vc, thumb, utils


@app.on_message(filters.command(["resume"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _resume(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])

    if await db.playing(m.chat.id):
        return await m.reply_text(m.lang["play_not_paused"])

    await anon.resume(m.chat.id)
    autoplay_status = await db.get_autoplay(m.chat.id)
    
    # Delete command message to keep chat clean
    try:
        await m.delete()
    except:
        pass
    
    # Get current media to edit player message
    media = await queue.get_current(m.chat.id)
    if media:
        # Restore the played_at timestamp from the saved elapsed time
        # so seekbar continues correctly
        import time
        elapsed = media.time if media.time else 0
        
        # Verify duration
        try:
            duration_sec = utils.to_seconds(media.duration)
        except:
            duration_sec = 0

        # Clamp elapsed to prevent overflows/garbage
        if elapsed < 0: elapsed = 0
        if duration_sec > 0 and elapsed > duration_sec: elapsed = duration_sec

        media.played_at = time.time() - elapsed
        await queue.update_current(m.chat.id, media)
        
        # Generate timer string safely
        try:
            timer = utils.make_progress_bar(elapsed, duration_sec)
        except Exception as e:
            from bot import logger
            logger.error(f"Timer generation failed: {e}")
            timer = None
            
        from bot import logger
        logger.info(f"Resume Debug: duration={media.duration} ({duration_sec}s) elapsed={elapsed} timer='{timer}'")
    else:
        elapsed = 0
        timer = None

    if media and media.message_id:
        _thumb = await thumb.generate(media)
        if not _thumb:
            _thumb = config.DEFAULT_THUMB
        
        text = f"▶️ <u><b>Stream Resumed</b></u>\n\n<b>Title:</b> <a href='{media.url}'>{media.title}</a>\n\n<b>Duration:</b> {media.duration}\n<b>Resumed by:</b> {m.from_user.mention}"
        
        try:
            await app.edit_message_media(
                chat_id=m.chat.id,
                message_id=media.message_id,
                media=InputMediaPhoto(media=_thumb, caption=text),
                reply_markup=buttons.controls(
                    chat_id=m.chat.id, 
                    autoplay=autoplay_status,
                    timer=timer
                ),
            )
        except:
            # Fallback to reply if edit fails
            await m.reply_text(
                text=m.lang["play_resumed"].format(m.from_user.mention),
                reply_markup=buttons.controls(
                    chat_id=m.chat.id, 
                    autoplay=autoplay_status,
                    timer=timer
                ),
            )
    else:
        await m.reply_text(
            text=m.lang["play_resumed"].format(m.from_user.mention),
            reply_markup=buttons.controls(
                chat_id=m.chat.id, 
                autoplay=autoplay_status,
                timer=timer
            ),
        )
