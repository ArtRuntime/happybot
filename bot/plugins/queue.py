# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types
from pyrogram.types import InputMediaPhoto

from bot import app, config, db, lang, logger, queue
from bot.helpers import Track, buttons, thumb, utils


# ─── /queue command ────────────────────────────────────────────────────────────

@app.on_message(filters.command("queue") & filters.group & ~app.bl_users)
@lang.language()
async def _queue_func(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])

    _reply = await m.reply_text(m.lang["queue_fetching"])
    _queue = await queue.get_queue(m.chat.id)
    _media = _queue[0]
    _thumb = (
        await thumb.generate(_media)
        if isinstance(_media, Track)
        else config.DEFAULT_THUMB
    )
    _text = m.lang["queue_curr"].format(
        _media.url,
        _media.title[:50],
        _media.duration,
        _media.user,
    )
    _queue.pop(0)

    if _queue:
        _text += "<blockquote expandable>"
        for i, media in enumerate(_queue, start=1):
            if i == 15:
                break
            _text += m.lang["queue_item"].format(
                i + 1, media.title, media.duration
            )
        _text += "</blockquote>"

    _playing = await db.playing(m.chat.id)
    await _reply.edit_media(
        media=types.InputMediaPhoto(
            media=_thumb,
            caption=_text,
        ),
        reply_markup=buttons.queue_markup(
            m.chat.id,
            m.lang["playing"] if _playing else m.lang["paused"],
            _playing,
        ),
    )


# ─── /playing command ──────────────────────────────────────────────────────────

@app.on_message(filters.command("playing") & filters.group & ~app.bl_users)
@lang.language()
async def _playing_func(_, m: types.Message):
    """Refresh the rich player UI — deletes the old player and sends a new one."""
    chat_id = m.chat.id

    if not await db.get_call(chat_id):
        return await m.reply_text(m.lang["not_playing"])

    media = await queue.get_current(chat_id)
    if not media:
        return await m.reply_text(m.lang["not_playing"])

    # Delete the command message to keep chat clean
    try:
        await m.delete()
    except Exception:
        pass

    # Delete the OLD player message (if tracked)
    if media.message_id:
        try:
            await app.delete_messages(chat_id, media.message_id)
        except Exception:
            pass

    # Build the same rich player as play_media
    _lang = await lang.get_lang(chat_id)
    _thumb_path = None
    if isinstance(media, Track):
        _thumb_path = await thumb.generate(media)
    if not _thumb_path:
        _thumb_path = config.DEFAULT_THUMB

    text = _lang["play_media"].format(
        media.url,
        media.title,
        media.duration,
        media.user,
    )

    autoplay_status = await db.get_autoplay(chat_id)
    is_playing = await db.playing(chat_id)

    # Progress bar
    try:
        duration_sec = utils.to_seconds(media.duration)
        timer = utils.make_progress_bar(0, duration_sec)
    except Exception:
        timer = None

    audio_track_count = len(getattr(media, "audio_streams", [])) if hasattr(media, "audio_streams") else 0

    keyboard = buttons.controls(
        chat_id,
        timer=timer,
        autoplay=autoplay_status,
        audio_tracks=audio_track_count,
    )

    # Send fresh player
    try:
        new_msg = await app.send_photo(
            chat_id=chat_id,
            photo=_thumb_path,
            caption=text,
            reply_markup=keyboard,
        )
        # Update tracked message_id so future controls target the new message
        media.message_id = new_msg.id
        await queue.update_current(chat_id, media)
        logger.info(f"🔄 Refreshed player UI for chat {chat_id} (new msg: {new_msg.id})")
    except Exception as e:
        logger.error(f"Failed to send fresh player in {chat_id}: {e}")
        await app.send_message(chat_id, m.lang["not_playing"])
