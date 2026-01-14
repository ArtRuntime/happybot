# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import asyncio
import time

from pyrogram import enums, errors, filters, types

from bot import anon, app, config, db, lang, queue, tasks, userbot, yt
from bot.helpers import buttons


@app.on_message(filters.video_chat_started, group=19)
@app.on_message(filters.video_chat_ended, group=20)
async def _watcher_vc(_, m: types.Message):
    await anon.stop(m.chat.id)


async def auto_leave():
    while True:
        await asyncio.sleep(1800)
        for ub in userbot.clients:
            left = 0
            try:
                for dialog in await ub.get_dialogs():
                    chat_id = dialog.chat.id
                    if left >= 20:
                        break
                    if chat_id in [app.logger, -1001686672798, -1001549206010]:
                        continue
                    if dialog.chat.type in [
                        enums.ChatType.GROUP,
                        enums.ChatType.SUPERGROUP,
                    ]:
                        if chat_id in db.active_calls:
                            continue
                        await ub.leave_chat(chat_id)
                        left += 1
                    await asyncio.sleep(5)
            except:
                continue


async def track_time():
    while True:
        await asyncio.sleep(1)
        for chat_id in list(db.active_calls):
            if not await db.playing(chat_id):
                continue
            media = await queue.get_current(chat_id)
            if not media:
                continue
            media.time += 1
            try:
                await queue.update_current(chat_id, media)
            except:
                pass


async def update_timer(length=10):
    while True:
        await asyncio.sleep(config.PLAYER_UPDATE_INTERVAL)
        for chat_id in list(db.active_calls):
            if not await db.playing(chat_id):
                continue
            try:
                media = await queue.get_current(chat_id)
                duration, message_id = media.duration_sec, media.message_id
                if not duration or not message_id or not media.time:
                    continue
                played = media.time
                remaining = duration - played
                pos = min(int((played / duration) * length), length - 1)
                timer = "—" * pos + "◉" + "—" * (length - pos - 1)

                if remaining <= 30:
                    next = await queue.get_next(chat_id, check=True)
                    if next and not next.file_path:
                        next.file_path = await yt.download(next.id, video=next.video)

                if remaining < 10:
                    remove = True
                else:
                    remove = False
                    if duration >= 3600:
                        fmt = "%H:%M:%S"
                    else:
                        fmt = "%M:%S"
                    timer = f"{time.strftime(fmt, time.gmtime(played))} | {timer} | -{time.strftime(fmt, time.gmtime(remaining))}"

                autoplay_status = await db.get_autoplay(chat_id)
                await app.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=buttons.controls(
                        chat_id=chat_id, timer=timer, remove=remove, autoplay=autoplay_status
                    ),
                )
            except Exception:
                pass


# AFK tracker - stores last activity time for each chat
afk_tracker = {}

async def vc_watcher(sleep=15):
    """AFK Protector - stops playback if no listeners for AFK_TIMEOUT seconds."""
    while True:
        await asyncio.sleep(sleep)
        for chat_id in list(db.active_calls):
            try:
                client = await db.get_assistant(chat_id)
                media = await queue.get_current(chat_id)
                if not media:
                    continue
                    
                participants = await client.get_participants(chat_id)
                listener_count = len(participants) - 1  # Exclude the bot itself
                
                if listener_count < 1:
                    # No listeners - track AFK time
                    if chat_id not in afk_tracker:
                        afk_tracker[chat_id] = time.time()
                    
                    afk_duration = time.time() - afk_tracker[chat_id]
                    
                    # Check if AFK timeout reached
                    if afk_duration >= config.AFK_TIMEOUT:
                        _lang = await lang.get_lang(chat_id)
                        try:
                            autoplay_status = await db.get_autoplay(chat_id)
                            await app.edit_message_reply_markup(
                                chat_id=chat_id,
                                message_id=media.message_id,
                                reply_markup=buttons.controls(
                                    chat_id=chat_id, status=_lang["stopped"], remove=True, autoplay=autoplay_status
                                ),
                            )
                            await anon.stop(chat_id)
                            afk_mins = config.AFK_TIMEOUT // 60
                            await app.send_message(chat_id, f"🛑 <b>Stopped due to inactivity.</b>\n\nNo listeners for {afk_mins} minutes.")
                            del afk_tracker[chat_id]
                        except errors.MessageIdInvalid:
                            pass
                else:
                    # Listeners present - reset AFK tracker
                    if chat_id in afk_tracker:
                        del afk_tracker[chat_id]
            except Exception:
                pass


if config.AUTO_END:
    tasks.append(asyncio.create_task(vc_watcher()))
if config.AUTO_LEAVE:
    tasks.append(asyncio.create_task(auto_leave()))
tasks.append(asyncio.create_task(track_time()))
tasks.append(asyncio.create_task(update_timer()))
