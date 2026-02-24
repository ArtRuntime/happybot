# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pathlib import Path

from pyrogram import filters, types

from bot import anon, app, config, db, lang, queue, tg, userbot, yt
from bot.helpers import buttons, utils
from bot.helpers._play import checkUB, join_assistant


async def playlist_to_queue(chat_id: int, tracks: list) -> str:
    text = "<blockquote expandable>"
    for track in tracks:
        pos = await queue.add(chat_id, track)
        text += f"<b>{pos}.</b> {track.title}\n"
    text = text[:1948] + "</blockquote>"
    return text

from collections import defaultdict
import asyncio

_play_locks = defaultdict(asyncio.Lock)

@app.on_message(
    filters.command(["play", "playforce", "vplay", "vplayforce"])
    & filters.group
    & ~app.bl_users
)
@lang.language()
@checkUB
async def play_hndlr(
    _,
    m: types.Message,
    force: bool = False,
    m3u8: bool = False,
    video: bool = False,
    url: str = None,
) -> None:
    if not userbot.clients:
        return await m.reply_text(
            "⚠️ **No Assistant Found!**\n\n"
            "The bot requires an assistant account to join the voice chat.\n"
            "Please go to my PM and send /login to add an assistant."
        )
    sent = await m.reply_text(m.lang["play_searching"])
    
    # Try to join VC in background (if not joined) while searching
    # This prevents the initial response delay
    if not await join_assistant(m, m.chat.id):
        return
        
    # Track queue position for this request; treat forced plays as position 0 (now playing)
    position = None

    async with _play_locks[m.chat.id]:
        file = None
        mention = m.from_user.mention
        tracks = []

        if url:
            if "playlist" in url:
                await sent.edit_text(m.lang["playlist_fetch"])
                tracks = await yt.playlist(
                    config.PLAYLIST_LIMIT, mention, url, video
                )

                if not tracks:
                    return await sent.edit_text(m.lang["playlist_error"])

                file = tracks[0]
                tracks.remove(file)
                file.message_id = sent.id
                # Mark as playlist to prevent autoplay interference
                file.req_type = "playlist"
            else:
                file = await yt.search(url, sent.id, video=video)
                # Mark YouTube/YT Music URLs for autoplay eligibility
                if file:
                    file.req_type = "youtube"

            if not file:
                return await sent.edit_text(
                    m.lang["play_not_found"].format(config.SUPPORT_CHAT)
                )

        elif len(m.command) >= 2:
            query = " ".join(m.command[1:])
            file = await yt.search(query, sent.id, video=video)
            if file:
                file.req_type = "search"
            if not file:
                return await sent.edit_text(
                    m.lang["play_not_found"].format(config.SUPPORT_CHAT)
                )

        # Check if user replied to a message containing a URL
        elif m.reply_to_message:
            extracted_url = utils.get_url(m)
            if extracted_url:
                # Found a URL in the replied message
                if "playlist" in extracted_url:
                    await sent.edit_text(m.lang["playlist_fetch"])
                    tracks = await yt.playlist(
                        config.PLAYLIST_LIMIT, mention, extracted_url, video
                    )

                    if not tracks:
                        return await sent.edit_text(m.lang["playlist_error"])

                    file = tracks[0]
                    tracks.remove(file)
                    file.message_id = sent.id
                    file.req_type = "playlist"
                else:
                    file = await yt.search(extracted_url, sent.id, video=video)
                    if file:
                        file.req_type = "youtube"

                if not file:
                    return await sent.edit_text(
                        m.lang["play_not_found"].format(config.SUPPORT_CHAT)
                    )
            else:
                # No URL found, check if it's an audio/video file
                media = tg.get_media(m.reply_to_message)
                if media:
                    setattr(sent, "lang", m.lang)
                    file = await tg.download(m.reply_to_message, sent)

        if not file:
            return await sent.edit_text(m.lang["play_usage"])
        
        # Block m3u8 live streams only (not Telegram files with unknown duration)
        # Telegram files can have duration_sec=0 if metadata isn't available
        if m3u8 and not file.duration_sec:
            return await sent.edit_text(m.lang["play_unsupported"])

        if await db.is_logger():
            await utils.play_log(m, file.title, file.duration)

        file.user = mention
        file.source = 'user'  # Mark as user-requested for recommendation training

        if force:
            # Force this track as the current one
            await queue.force_add(m.chat.id, file)
            position = 0
            # Mark queue as loading since we're about to start playback
            await queue.set_loading(m.chat.id, True)
        else:
            position = await queue.add(m.chat.id, file)

            # Check if song was queued (position > 0) OR if queue thinks something is playing
            # BUT double check if bot is actually connected to VC
            is_active = await db.get_call(m.chat.id)
            
            # Detect Zombie State: Redis has 'current' (so pos > 0), but pytgcalls is disconnected
            # AND NOT LOADING (new check)
            is_loading = await queue.is_loading(m.chat.id)
            if position != 0 and not is_active and not is_loading:
                # Zombie state detected! Clear old state and force this song to play
                await queue.remove_current(m.chat.id)
                # Re-add as current (pos 0) via force_add logic simulation or just call play
                # Simpler: just set as current manually since we know it's empty now
                await queue.update_current(m.chat.id, file)
                position = 0
                # Proceed to play logic below...

            if position == 0:
                await queue.set_loading(m.chat.id, True)

            if position != 0:
                await sent.edit_text(
                    m.lang["play_queued"].format(
                        position,
                        file.url,
                        file.title,
                        file.duration,
                        m.from_user.mention,
                    ),
                    reply_markup=buttons.play_queued(
                        m.chat.id, position, m.lang["play_now"]
                    ),
                )
                
                if tracks:
                    added = await playlist_to_queue(m.chat.id, tracks)
                    await app.send_message(
                        chat_id=m.chat.id,
                        text=m.lang["playlist_queued"].format(len(tracks)) + added,
                    )
                return

    # Lock released here. Proceed to download/play
    try:
        if not file.file_path:
            # Check for any existing file with this ID regardless of extension
            search_path = Path(f"downloads/{file.id}.*")
            found_files = list(Path("downloads").glob(f"{file.id}.*"))
            
            if found_files:
                file.file_path = str(found_files[0])
            else:
                # Use direct streaming or download based on config
                if config.ENABLE_DIRECT_STREAMING and file.req_type != "telegram" and not file.url.startswith("t.me") and not video:
                    # Direct streaming for YouTube/external URLs
                    await sent.edit_text("🔎 Loading Stream...")
                    try:
                        quality = await db.get_quality(chat_id)
                        file.file_path = await yt.get_stream_url(file.id, video=video, quality=quality)
                        if not file.file_path:
                            # Fallback to download if streaming fails
                            file.file_path = await yt.download(file.id, video=video)
                    except Exception as e:
                        # Fallback to download on any error
                        file.file_path = await yt.download(file.id, video=video)
                else:
                    # Download for Telegram files or if streaming disabled
                    await sent.edit_text(m.lang["play_downloading"])
                    try:
                        file.file_path = await yt.download(file.id, video=video)
                    except yt.StorageLowError:
                        return await sent.edit_text(m.lang["error_low_storage"].format(config.SUPPORT_CHAT))

        await anon.play_media(chat_id=m.chat.id, message=sent, media=file)
        if not tracks:
            return
        added = await playlist_to_queue(m.chat.id, tracks)
        await app.send_message(
            chat_id=m.chat.id,
            text=m.lang["playlist_queued"].format(len(tracks)) + added,
        )
    finally:
        # Only clear loading flag if we actually marked this request as "now playing"
        if position == 0:
            await queue.set_loading(m.chat.id, False)
