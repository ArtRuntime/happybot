# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types
from pyrogram.types import InputMediaPhoto

from bot import anon, app, config, db, lang, queue
from bot.helpers import buttons, can_manage_vc, thumb


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
    media = queue.get_current(m.chat.id)
    if media and media.message_id:
        _thumb = await thumb.generate(media)
        if not _thumb:
            _thumb = config.DEFAULT_THUMB
        
        text = f"▶️ <u><b>Stream Resumed</b></u>\n\n<b>Title:</b> <a href='{media.url}'>{media.title}</a>\n\n<b>Duration:</b> {media.duration} min\n<b>Resumed by:</b> {m.from_user.mention}"
        
        try:
            await app.edit_message_media(
                chat_id=m.chat.id,
                message_id=media.message_id,
                media=InputMediaPhoto(media=_thumb, caption=text),
                reply_markup=buttons.controls(m.chat.id, autoplay=autoplay_status),
            )
        except:
            # Fallback to reply if edit fails
            await m.reply_text(
                text=m.lang["play_resumed"].format(m.from_user.mention),
                reply_markup=buttons.controls(m.chat.id, autoplay=autoplay_status),
            )
    else:
        await m.reply_text(
            text=m.lang["play_resumed"].format(m.from_user.mention),
            reply_markup=buttons.controls(m.chat.id, autoplay=autoplay_status),
        )
