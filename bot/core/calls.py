# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import asyncio
import os
from ntgcalls import (ConnectionNotFound, TelegramServerError,
                      RTMPStreamingUnsupported)
from pyrogram.errors import MessageIdInvalid
from pyrogram.types import InputMediaPhoto, Message
from pytgcalls import PyTgCalls, exceptions, types
from pytgcalls.pytgcalls_session import PyTgCallsSession

from bot import app, config, db, lang, logger, queue, userbot, yt
from bot.helpers import Media, Track, buttons, thumb, utils


class TgCall(PyTgCalls):
    def __init__(self):
        self.clients = []

    async def pause(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=True)
        return await client.pause(chat_id)

    async def resume(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=False)
        return await client.resume(chat_id)

    async def stop(self, chat_id: int) -> None:
        client = await db.get_assistant(chat_id)
        
        # Cancel any active downloads for this chat
        yt.cancel_downloads(chat_id)
        
        # Cancel any active preload for this chat
        if chat_id in self._preload_tasks:
            self._preload_cancelled.add(chat_id)
            try:
                self._preload_tasks[chat_id].cancel()
            except:
                pass
        
        # Cleanup current song and update UI
        media = queue.get_current(chat_id)
        if media:
            # Update player message to "Stopped" state
            if media.message_id:
                try:
                    _lang = await lang.get_lang(chat_id)
                    autoplay_status = await db.get_autoplay(chat_id)
                    await app.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=media.message_id,
                        reply_markup=buttons.controls(
                            chat_id=chat_id, 
                            status=_lang["stopped"], 
                            remove=True,
                            autoplay=autoplay_status
                        ),
                    )
                except:
                    pass

            if media.file_path and os.path.exists(media.file_path):
                try:
                    os.remove(media.file_path)
                except:
                    pass
            
            # Cleanup thumbnail
            thumb_path = f"cache/{media.id}.png"
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass
        
        # Cleanup ALL queued songs (including preloaded/cached ones)
        all_queued = queue.get_queue(chat_id)
        if all_queued:
            for item in all_queued:
                if item.file_path and os.path.exists(item.file_path):
                    try:
                        os.remove(item.file_path)
                        logger.info(f"Cleaned up cached file: {item.file_path}")
                    except:
                        pass
                # Cleanup thumbnail
                thumb_path = f"cache/{item.id}.png"
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except:
                        pass

        try:
            queue.clear(chat_id)
            await db.remove_call(chat_id)
        except:
            pass

        try:
            await client.leave_call(chat_id, close=False)
        except:
            pass

    # Track active preload tasks per chat
    _preload_tasks: dict[int, asyncio.Task] = {}
    _preload_cancelled: set[int] = set()

    async def _preload_next_song(self, chat_id: int, current_track: Track) -> None:
        """Proactively predict and download the next song in background."""
        next_track = None
        try:
            mode = await db.get_autoplay(chat_id)
            if not mode:
                return
            
            # Check if cancelled before starting
            if chat_id in self._preload_cancelled:
                self._preload_cancelled.discard(chat_id)
                return
            
            # Predict next song
            next_track = await yt.smart_autoplay(mode, previous_track=current_track)
            if not next_track:
                logger.info(f"Autoplay preload: No prediction for chat {chat_id}")
                return
            
            # Mark as autoplay (don't use for recommendation training)
            next_track.source = 'autoplay'
            
            # Re-check autoplay status before downloading (might have been toggled off)
            mode = await db.get_autoplay(chat_id)
            if not mode:
                logger.info(f"Autoplay preload: Cancelled - autoplay disabled for chat {chat_id}")
                return
            
            # Check if cancelled before downloading
            if chat_id in self._preload_cancelled:
                self._preload_cancelled.discard(chat_id)
                return
            
            # Check if call is still active before downloading
            if not await db.get_call(chat_id):
                logger.info(f"Autoplay preload: Cancelled - call ended for chat {chat_id}")
                return
            
            # Original check if cancelled before downloading
            if chat_id in self._preload_cancelled:
                self._preload_cancelled.discard(chat_id)
                return
            
            # Get file/stream URL
            from bot import config
            if config.ENABLE_DIRECT_STREAMING and not next_track.url.startswith("t.me"):
                # Direct streaming for YouTube/external URLs
                next_track.file_path = await yt.get_stream_url(next_track.id, video=next_track.video)
                if not next_track.file_path:
                    logger.warning(f"Stream URL extraction failed, falling back to download")
                    next_track.file_path = await yt.download(next_track.id, video=next_track.video)
            else:
                # Download for Telegram files or if streaming disabled
                next_track.file_path = await yt.download(next_track.id, video=next_track.video)
            
            # Check if cancelled after download (cleanup if needed)
            if chat_id in self._preload_cancelled:
                self._preload_cancelled.discard(chat_id)
                if next_track.file_path and os.path.exists(next_track.file_path):
                    try:
                        os.remove(next_track.file_path)
                        logger.info(f"Autoplay preload: Cleaned cancelled download: {next_track.file_path}")
                    except:
                        pass
                return
            
            if not next_track.file_path:
                logger.warning(f"Autoplay preload: Download failed for {next_track.title}")
                return
            
            # Re-check autoplay status before adding to queue
            # Check if cancelled after download (cleanup if needed)
            if chat_id in self._preload_cancelled:
                self._preload_cancelled.discard(chat_id)
                if next_track.file_path and os.path.exists(next_track.file_path):
                    try:
                        os.remove(next_track.file_path)
                    except:
                        pass
                return
            
            # Check for failed extraction
            if not next_track.file_path:
               logger.warning(f"Autoplay preload: Failed to get stream/file for {next_track.title}")
               return

            # CRITICAL: Re-check if call is still active before adding to queue
            # This prevents adding songs after user pressed stop
            if not await db.get_call(chat_id):
                logger.info(f"Autoplay preload: Call ended during download - cleaning up {next_track.file_path}")
                if next_track.file_path and os.path.exists(next_track.file_path):
                    try:
                        os.remove(next_track.file_path)
                    except:
                        pass
                return
            
            # Add to queue (if still no next song and call is active)
            if await db.get_call(chat_id) and not queue.get_next(chat_id, check=True):
                queue.add(chat_id, next_track)
                logger.info(f"Autoplay preload: Queued '{next_track.title}' for chat {chat_id}")
            else:
                # If call ended or song already in queue, cleanup the downloaded file
                if next_track.file_path and os.path.exists(next_track.file_path):
                    try:
                        os.remove(next_track.file_path)
                        logger.info(f"Autoplay preload: Cleaned unused download: {next_track.file_path}")
                    except:
                        pass
        except asyncio.CancelledError:
            logger.info(f"Autoplay preload: Cancelled for chat {chat_id}")
            # Cleanup if download was in progress
            if next_track and next_track.file_path and os.path.exists(next_track.file_path):
                try:
                    os.remove(next_track.file_path)
                    logger.info(f"Autoplay preload: Cleaned cancelled file: {next_track.file_path}")
                except:
                    pass
        except Exception as e:
            logger.warning(f"Autoplay preload error: {e}")
            # Cleanup on error
            if next_track and next_track.file_path and os.path.exists(next_track.file_path):
                try:
                    os.remove(next_track.file_path)
                except:
                    pass
        finally:
            # Remove from active tasks
            if chat_id in self._preload_tasks:
                del self._preload_tasks[chat_id]

    async def prepare_track(self, chat_id: int, track: Track) -> None:
        """
        Background task to prepare (stream/download) a track 
        so it's ready for instant playback.
        """
        if track.file_path:
            return  # Already ready

        logger.info(f"🔄 Preparing track in background: {track.title}")
        
        from bot import config
        
        try:
            # 1. Try Direct Streaming (if enabled)
            if config.ENABLE_DIRECT_STREAMING and track.req_type != "telegram" and not track.url.startswith("t.me"):
                track.file_path = await yt.get_stream_url(track.id, video=track.video)
                if track.file_path:
                    logger.info(f"✅ Track prepared (Stream): {track.title}")
                    return

            # 2. Fallback to Download (if stream failed or disabled)
            logger.info(f"⬇️ Preparing track (Download): {track.title}")
            track.file_path = await yt.download(track.id, video=track.video)
            
            if track.file_path:
                 logger.info(f"✅ Track prepared (Downloaded): {track.file_path}")

        except Exception as e:
            logger.error(f"Failed to prepare track {track.title}: {e}")

    async def play_media(
        self,
        chat_id: int,
        message: Message,
        media: Media | Track,
        seek_time: int = 0,
    ) -> None:
        client = await db.get_assistant(chat_id)
        _lang = await lang.get_lang(chat_id)
        _thumb = None
        if isinstance(media, Track):
            _thumb = await thumb.generate(media)
        
        if not _thumb or not os.path.exists(_thumb):
            _thumb = config.DEFAULT_THUMB

        if not media.file_path:
            await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
            return await self.play_next(chat_id)

        # Build ffmpeg parameters
        ffmpeg_params = f"-ss {seek_time}" if seek_time > 1 else None
        
        # Add headers for anime streams to bypass 403 Forbidden
        if getattr(media, 'req_type', None) == 'anime' and media.file_path.startswith("http"):
            headers = (
                "Referer: https://hianime.to\r\n"
                "Origin: https://hianime.to\r\n"
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            header_param = f'-headers "{headers}"'
            ffmpeg_params = f"{header_param} {ffmpeg_params}" if ffmpeg_params else header_param
        
        stream = types.MediaStream(
            media_path=media.file_path,
            audio_parameters=types.AudioQuality.HIGH,
            video_parameters=types.VideoQuality.HD_720p,
            audio_flags=types.MediaStream.Flags.REQUIRED,
            video_flags=(
                types.MediaStream.Flags.AUTO_DETECT
                if media.video
                else types.MediaStream.Flags.IGNORE
            ),
            ffmpeg_parameters=ffmpeg_params,
        )
        try:
            await client.play(
                chat_id=chat_id,
                stream=stream,
                config=types.GroupCallConfig(auto_start=False),
            )
            # Force unpause and update DB status
            await client.resume(chat_id)
            await db.playing(chat_id, paused=False)
            if not seek_time:
                media.time = 1
                await db.add_call(chat_id)
                
                # Track this song for building recommendation dataset
                try:
                    from datetime import datetime
                    await db.db['played_songs'].insert_one({
                        'video_id': media.id,
                        'title': media.title,
                        'channel': getattr(media, 'channel_name', 'Unknown'),
                        'duration': getattr(media, 'duration', 'Unknown'),
                        'url': getattr(media, 'url', ''),
                        'played_at': datetime.now(),
                        'chat_id': chat_id,
                        'source': getattr(media, 'source', 'unknown'),  # user/autoplay
                        'req_type': getattr(media, 'req_type', 'unknown'),  # search/youtube/telegram
                    })
                except Exception as e:
                    # Silent fail - don't break playback
                    logger.debug(f"Failed to track song for recommendations: {e}")
                
                text = _lang["play_media"].format(
                    media.url,
                    media.title,
                    media.duration,
                    media.user,
                )
                autoplay_status = await db.get_autoplay(chat_id)
                
                # Generate progress bar
                try:
                    duration_sec = utils.to_seconds(media.duration)
                    timer = utils.make_progress_bar(0, duration_sec)
                except Exception as e:
                    timer = None
                
                keyboard = buttons.controls(chat_id, timer=timer, autoplay=autoplay_status)
                try:
                    await message.edit_media(
                        media=InputMediaPhoto(
                            media=_thumb,
                            caption=text,
                        ),
                        reply_markup=keyboard,
                    )
                    # Update message_id to track the edited message
                    media.message_id = message.id
                except MessageIdInvalid:
                    media.message_id = (await app.send_photo(
                        chat_id=chat_id,
                        photo=_thumb,
                        caption=text,
                        reply_markup=keyboard,
                    )).id
                
                
                # Proactive autoplay preload - predict and download next song in background
                # Skip autoplay for anime - only works for music
                is_anime = getattr(media, 'req_type', None) == 'anime'
                if autoplay_status and not queue.get_next(chat_id, check=True) and not is_anime:
                    # Cancel any existing preload task to prevent duplicates
                    if chat_id in self._preload_tasks:
                        old_task = self._preload_tasks[chat_id]
                        if not old_task.done():
                            old_task.cancel()
                            logger.info(f"Cancelled previous preload task for chat {chat_id}")
                    
                    task = asyncio.create_task(self._preload_next_song(chat_id, media))
                    self._preload_tasks[chat_id] = task
        except FileNotFoundError:
            await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
            await self.play_next(chat_id)
        except exceptions.NoActiveGroupCall:
            await self.stop(chat_id)
            await message.edit_text(_lang["error_no_call"])
        except exceptions.NoAudioSourceFound:
            # Fallback to download if streaming failed
            if media.file_path and media.file_path.startswith("http"):
                try:
                    await message.edit_text("📥 Stream failed, downloading...")
                    logger.warning(f"Stream failed for {media.title}, falling back to download")
                    
                    # For anime, download from the stream URL directly
                    if getattr(media, 'req_type', None) == 'anime':
                        logger.info(f"Downloading anime from URL: {media.file_path}")
                        new_path = await yt.download(media.file_path, video=media.video)
                    else:
                        new_path = await yt.download(media.id, video=media.video)
                    
                    if new_path:
                        media.file_path = new_path
                        # Recursive retry with downloaded file
                        return await self.play_media(chat_id, message, media, seek_time)
                except Exception as e:
                    logger.error(f"Fallback download failed: {e}")
                    
                    # Show specific error for anime 403 Forbidden
                    if getattr(media, 'req_type', None) == 'anime' and '403' in str(e):
                        await message.edit_text(
                            "❌ **Anime Stream Blocked (403 Forbidden)**\n\n"
                            "The anime streaming server is blocked or requires authentication.\n"
                            "This usually means the CDN has geo-restrictions or the URL has expired.\n\n"
                            "**Try:**\n"
                            "• Selecting a different server using 🌐 Server button\n"
                            "• Trying another anime\n"
                            "• Using a VPN if available"
                        )
                        return  # Don't play next

            # Don't auto-play next for anime failures
            if getattr(media, 'req_type', None) != 'anime':
                await message.edit_text(_lang["error_no_audio"])
                await self.play_next(chat_id)
            else:
                # For anime, show error and stop - don't trigger music autoplay
                await message.edit_text(
                    "❌ **Failed to play anime**\n\n"
                    "The stream failed and download also failed.\n\n"
                    "**Try:**\n"
                    "• Selecting a different server\n"
                    "• Trying another episode\n"
                    "• Checking your connection"
                )
                await self.stop(chat_id)
        except (ConnectionNotFound, TelegramServerError):
            await self.stop(chat_id)
            await message.edit_text(_lang["error_tg_server"])
        except RTMPStreamingUnsupported:
            await self.stop(chat_id)
            await message.edit_text(_lang["error_rtmp"])


    async def replay(self, chat_id: int) -> None:
        if not await db.get_call(chat_id):
            return

        media = queue.get_current(chat_id)
        _lang = await lang.get_lang(chat_id)
        msg = await app.send_message(chat_id=chat_id, text=_lang["play_again"])
        await self.play_media(chat_id, msg, media)


    async def play_next(self, chat_id: int) -> None:
        # Cleanup previous track
        old_media = queue.get_playing(chat_id)
        if old_media:
            # Disable buttons on previous song message
            if hasattr(old_media, 'message_id') and old_media.message_id:
                try:
                    await app.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=old_media.message_id,
                        reply_markup=None
                    )
                except Exception as e:
                    logger.error(f"Failed to cleanup buttons for {old_media.title}: {e}")
            if old_media.file_path and os.path.exists(old_media.file_path):
                try:
                    os.remove(old_media.file_path)
                except:
                    pass
            
            # Cleanup thumbnail
            thumb_path = f"cache/{old_media.id}.png"
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass

        media = queue.get_next(chat_id)
        try:
            if media.message_id:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=media.message_id,
                    revoke=True,
                )
                media.message_id = 0
        except:
            pass

        if not media:
            # Autoplay ONLY for YouTube search and YouTube/YT Music URLs
            # Everything else (Telegram files, anime, playlists) = no autoplay
            if old_media:
                old_req_type = getattr(old_media, 'req_type', None)
                
                # Only allow autoplay for YouTube search, direct YouTube URLs, playlists, and previous autoplay tracks
                if old_req_type not in ['search', 'youtube', 'autoplay', 'playlist']:
                    logger.info(f"Skipping autoplay - req_type '{old_req_type}' not eligible for autoplay")
                    return await self.stop(chat_id)
                
                # Check if autoplay enabled
                mode = await db.get_autoplay(chat_id)
                new_track = None
                if mode:
                    # Autoplay logic with TF-IDF smart mode
                    new_track = await yt.smart_autoplay(mode, previous_track=old_media)
                
                # Check if user added a song while we were fetching autoplay
                # If yes, prioritize user song and discard/ignore the autoplay result
                if queue.get_queue(chat_id):
                    logger.info(f"User added song during autoplay fetch in {chat_id} - Switching to user track")
                    media = queue.get_next(chat_id)
                elif new_track:
                    # Add to queue
                    queue.add(chat_id, new_track)
                    media = new_track # Set media to the new track
                    
                    # Notify user about autoplay
                    _lang = await lang.get_lang(chat_id)
                    try:
                        await app.send_message(
                            chat_id=chat_id,
                            text=f"<b>Autoplay:</b> Adding <i>{new_track.title}</i> to queue..."
                        )
                    except:
                        pass
                    # Do NOT recurse. Proceed to play loop below.
                else:
                    # Autoplay failed - notify user
                    logger.warning(f"Autoplay failed to fetch next track for chat {chat_id}")
                    try:
                        await app.send_message(
                            chat_id=chat_id,
                            text="⚠️ <b>Autoplay failed</b>\n\nCouldn't fetch the next song. Playback stopped."
                        )
                    except:
                        pass
                    return await self.stop(chat_id)
            else:
                return await self.stop(chat_id)

        _lang = await lang.get_lang(chat_id)
        
        # Show appropriate message based on streaming/downloading
        from bot import config
        if config.ENABLE_DIRECT_STREAMING and media.req_type != "telegram" and not media.url.startswith("t.me"):
            msg = await app.send_message(chat_id=chat_id, text="⏭️ Loading next track...")
        else:
            msg = await app.send_message(chat_id=chat_id, text=_lang["play_next"])
        
        # Download or get stream URL
        if media.req_type != "telegram":
            if config.ENABLE_DIRECT_STREAMING and not media.url.startswith("t.me"):
                # Direct streaming for YouTube/external URLs
                logger.info(f"🎵 Using direct streaming for: {media.title}")
                media.file_path = await yt.get_stream_url(media.id, video=media.video)
                if not media.file_path:
                    logger.warning(f"Stream URL extraction failed, falling back to download")
                    media.file_path = await yt.download(media.id, video=media.video)
            else:
                # Download for Telegram files or if streaming disabled
                media.file_path = await yt.download(media.id, video=media.video)
            if not media.file_path:
                await self.stop(chat_id)
                return await msg.edit_text(
                    _lang["error_no_file"].format(config.SUPPORT_CHAT)
                )

        media.message_id = msg.id
        await self.play_media(chat_id, msg, media)


    async def ping(self) -> float:
        pings = [client.ping for client in self.clients]
        return round(sum(pings) / len(pings), 2)


    async def decorators(self, client: PyTgCalls) -> None:
        for client in self.clients:
            @client.on_update()
            async def update_handler(_, update: types.Update) -> None:
                if isinstance(update, types.StreamEnded):
                    if update.stream_type == types.StreamEnded.Type.AUDIO:
                        await self.play_next(update.chat_id)
                elif isinstance(update, types.ChatUpdate):
                    if update.status in [
                        types.ChatUpdate.Status.KICKED,
                        types.ChatUpdate.Status.LEFT_GROUP,
                        types.ChatUpdate.Status.CLOSED_VOICE_CHAT,
                    ]:
                        await self.stop(update.chat_id)


    async def add_pytgcalls_client(self, userbot_client) -> PyTgCalls:
        """
        Dynamically add a PyTgCalls client for a new assistant.
        
        Args:
            userbot_client: The Pyrogram userbot client
            
        Returns:
            The started PyTgCalls client
        """
        client = PyTgCalls(userbot_client, cache_duration=100)
        await client.start()
        self.clients.append(client)
        await self.decorators(client)
        logger.info(f"PyTgCalls client added for {userbot_client.name}")
        return client

    async def remove_pytgcalls_client(self, userbot_client) -> bool:
        """
        Dynamically remove a PyTgCalls client.
        
        Args:
            userbot_client: The Pyrogram userbot client to remove
            
        Returns:
            True if removed, False if not found
        """
        # Find the PyTgCalls client for this userbot
        tgcalls_client = None
        for client in self.clients:
            if client.session == userbot_client:
                tgcalls_client = client
                break
        
        if not tgcalls_client:
            return False
        
        # Remove from list
        self.clients.remove(tgcalls_client)
        logger.info(f"PyTgCalls client removed for {userbot_client.name}")
        return True

    async def boot(self) -> None:
        PyTgCallsSession.notice_displayed = True
        for ub in userbot.clients:
            await self.add_pytgcalls_client(ub)
        logger.info("PyTgCalls client(s) started.")
