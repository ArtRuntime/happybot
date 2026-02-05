# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import re

from pyrogram import filters, types

from bot import anon, app, db, lang, queue, tg, yt
from bot.helpers import admin_check, buttons, can_manage_vc


@app.on_callback_query(filters.regex("cancel_dl") & ~app.bl_users)
@lang.language()
async def cancel_dl(_, query: types.CallbackQuery):
    await query.answer()
    await tg.cancel(query)


@app.on_callback_query(filters.regex("controls") & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _controls(_, query: types.CallbackQuery):
    args = query.data.split()
    action, chat_id = args[1], int(args[2])
    qaction = len(args) == 4
    user = query.from_user.mention

    if not await db.get_call(chat_id):
        return await query.answer(query.lang["not_playing"], show_alert=True)

    if action == "status":
        return await query.answer()
        
    # Check if the button click is from the current player message
    current = await queue.get_current(chat_id)
    if not current:
        return await query.answer(query.lang["not_playing"], show_alert=True)
        
    # Skip check for force actions as they might be from other messages
    if action not in ["force"] and getattr(current, "message_id", 0) != query.message.id:
        return await query.answer("❌ This control panel is expired.", show_alert=True)
    
    
    # Handle autoplay toggle - show menu to select mode/genre
    if action == "autoplay":
        current = await db.get_autoplay(chat_id)
        # Show autoplay menu
        keyboard = buttons.autoplay_menu(chat_id, current)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return


    await query.answer(query.lang["processing"], show_alert=True)

    try:
        if action == "pause":
            if not await db.playing(chat_id):
                return await query.answer(
                    query.lang["play_already_paused"], show_alert=True
                )
            await anon.pause(chat_id)
            if qaction:
                return await query.edit_message_reply_markup(
                    reply_markup=buttons.queue_markup(chat_id, query.lang["paused"], False)
                )
            status = query.lang["paused"]
            reply = query.lang["play_paused"].format(user)

        elif action == "resume":
            if await db.playing(chat_id):
                return await query.answer(query.lang["play_not_paused"], show_alert=True)
            await anon.resume(chat_id)
            if qaction:
                return await query.edit_message_reply_markup(
                    reply_markup=buttons.queue_markup(chat_id, query.lang["playing"], True)
                )
            reply = query.lang["play_resumed"].format(user)

        elif action == "skip":
            await anon.play_next(chat_id)
            status = query.lang["skipped"]
            reply = query.lang["play_skipped"].format(user)

        elif action == "force":
            position = int(args[3])  # Now it's a position, not item_id
            _q = await queue.get_queue(chat_id)
            media = _q[position] if position < len(_q) else None
            
            if not media:
                return await query.edit_message_text(query.lang["play_expired"])

            m_id = (await queue.get_current(chat_id)).message_id
            await queue.force_add(chat_id, media, remove=position)
            try:
                await app.delete_messages(
                    chat_id=chat_id, message_ids=[m_id, media.message_id], revoke=True
                )
                media.message_id = None
            except:
                pass

            # Show appropriate message
            from bot import config
            if config.ENABLE_DIRECT_STREAMING and media.req_type != "telegram" and not media.url.startswith("t.me"):
                msg_text = "⏭️ Loading next track..."
            else:
                msg_text = query.lang["play_next"]

            msg = await app.send_message(chat_id=chat_id, text=msg_text)
            if not media.file_path:
                # Use streaming if enabled
                if config.ENABLE_DIRECT_STREAMING and media.req_type != "telegram" and not media.url.startswith("t.me"):
                    media.file_path = await yt.get_stream_url(media.id, video=media.video)
                    if not media.file_path:
                        media.file_path = await yt.download(media.id, video=media.video)
                else:
                    media.file_path = await yt.download(media.id, video=media.video)
            media.message_id = msg.id
            return await anon.play_media(chat_id, msg, media)

        elif action == "replay":
            media = await queue.get_current(chat_id)
            media.user = user
            await anon.replay(chat_id)
            status = query.lang["replayed"]
            reply = query.lang["play_replayed"].format(user)

        elif action == "stop":
            await anon.stop(chat_id)
            status = query.lang["stopped"]
            reply = query.lang["play_stopped"].format(user)
    except ValueError as e:
        if "No active sessions" in str(e):
             return await query.answer("⚠️ No Assistant Found!\nPlease login first with /login in PM.", show_alert=True)
        raise e

    try:
        if action in ["skip", "replay", "stop"]:
            await query.message.reply_text(reply, quote=False)
            await query.message.delete()
        else:
            # Get current media for updated caption
            media = await queue.get_current(chat_id)
            autoplay_status = await db.get_autoplay(chat_id)
            
            if action == "pause" and media:
                new_caption = f"⏸️ <u><b>Stream Paused</b></u>\n\n<b>Title:</b> <a href='{media.url}'>{media.title}</a>\n\n<b>Duration:</b> {media.duration}\n<b>Paused by:</b> {user}"
            elif action == "resume" and media:
                new_caption = f"▶️ <u><b>Stream Resumed</b></u>\n\n<b>Title:</b> <a href='{media.url}'>{media.title}</a>\n\n<b>Duration:</b> {media.duration}\n<b>Resumed by:</b> {user}"
            else:
                # Fallback to old behavior for other cases
                mtext = re.sub(
                    r"\n\n<blockquote>.*?</blockquote>",
                    "",
                    query.message.caption.html if query.message.caption else query.message.text.html,
                    flags=re.DOTALL,
                )
                new_caption = f"{mtext}\n\n<blockquote>{reply}</blockquote>"
            
            # Get audio track count from current media
            audio_track_count = 0
            if media:
                audio_streams = getattr(media, 'audio_streams', [])
                audio_track_count = len(audio_streams) if audio_streams else 0
            
            keyboard = buttons.controls(
                chat_id, status=status if action == "pause" else None, autoplay=autoplay_status, audio_tracks=audio_track_count
            )
            await query.edit_message_caption(
                caption=new_caption, reply_markup=keyboard
            )
    except:
        pass


@app.on_callback_query(filters.regex("help") & ~app.bl_users)
@lang.language()
async def _help(_, query: types.CallbackQuery):
    data = query.data.split()
    if len(data) == 1:
        return await query.answer(url=f"https://t.me/{app.username}?start=help")

    if data[1] == "back":
        return await query.edit_message_text(
            text=query.lang["help_menu"], reply_markup=buttons.help_markup(query.lang)
        )
    elif data[1] == "close":
        try:
            await query.message.delete()
            return await query.message.reply_to_message.delete()
        except:
            pass
        return

    await query.edit_message_text(
        text=query.lang[f"help_{data[1]}"],
        reply_markup=buttons.help_markup(query.lang, True),
    )


@app.on_callback_query(filters.regex("settings") & ~app.bl_users)
@lang.language()
@admin_check
async def _settings_cb(_, query: types.CallbackQuery):
    cmd = query.data.split()
    if len(cmd) == 1:
        return await query.answer()
    await query.answer(query.lang["processing"], show_alert=True)

    chat_id = query.message.chat.id
    _admin = await db.get_play_mode(chat_id)
    _delete = await db.get_cmd_delete(chat_id)
    _language = await db.get_lang(chat_id)

    if cmd[1] == "delete":
        _delete = not _delete
        await db.set_cmd_delete(chat_id, _delete)
    elif cmd[1] == "play":
        await db.set_play_mode(chat_id, _admin)
        _admin = not _admin
    await query.edit_message_reply_markup(
        reply_markup=buttons.settings_markup(
            query.lang,
            _admin,
            _delete,
            _language,
            chat_id,
        )
    )
