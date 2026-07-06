# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import asyncio
import os
from collections import defaultdict
from ntgcalls import (ConnectionNotFound, TelegramServerError,
                      RTMPStreamingUnsupported)
from pyrogram.errors import MessageIdInvalid, MessageNotModified
from pyrogram.types import InputMediaPhoto, Message
from pytgcalls import PyTgCalls, exceptions, types
from pytgcalls.pytgcalls_session import PyTgCallsSession
from pyrogram.raw import functions

from bot import app, config, db, lang, logger, queue, userbot, yt
from bot.helpers import Media, Track, buttons, thumb, utils


class TgCall(PyTgCalls):
    def __init__(self):
        self.clients = []
        self._client_map = {}
        self._consecutive_failures: dict[int, int] = defaultdict(int)
        self._play_next_locks: dict[int, asyncio.Lock] = {}
        self._watchdog_tasks: dict[int, asyncio.Task] = {}  # Watchdog for stuck streams
        self._unmute_keeper_tasks: dict[int, asyncio.Task] = {}  # Periodic unmute keeper
        self._connection_cache: dict[int, float] = {}  # Cache for successful connection checks
        self._last_rejoin: dict[int, float] = {}  # Timestamp of last rejoin per chat (cooldown)

    async def pause(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=True)
        # Cancel watchdog when pausing to prevent auto-resume
        self._cancel_watchdog(chat_id)
        return await client.pause(chat_id)

    async def resume(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=False)
        result = await client.resume(chat_id)
        
        # Restart watchdog with remaining duration when resuming
        try:
            media = await queue.get_current(chat_id)
            if media and hasattr(media, 'duration'):
                import time
                played_at = getattr(media, 'played_at', time.time())
                elapsed = time.time() - played_at
                remaining = max(0, media.duration - int(elapsed))
                if remaining > 0:
                    await self._start_watchdog(chat_id, remaining)
        except Exception as e:
            logger.error(f"Failed to restart watchdog on resume: {e}")
        
        return result

    async def stop(self, chat_id: int) -> None:
        try:
            client = await db.get_assistant(chat_id)
        except Exception:
            client = None
        
        # Cancel any active downloads for this chat
        yt.cancel_downloads(chat_id)
        
        # Cancel any active preload for this chat
        if chat_id in self._preload_tasks:
            self._preload_cancelled.add(chat_id)
            try:
                self._preload_tasks[chat_id].cancel()
            except:
                pass
        
        # Cancel watchdog timer
        self._cancel_watchdog(chat_id)
        
        # Cancel unmute keeper
        self._cancel_unmute_keeper(chat_id)
        
        # Cleanup current song and update UI
        media = await queue.get_current(chat_id)
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

            # We keep the file in cache now
            # if media.file_path and os.path.exists(media.file_path):
            #     try:
            #         await asyncio.to_thread(os.remove, media.file_path)
            #     except:
            #         pass
            
            # Cleanup thumbnail
            thumb_path = f"cache/{media.id}.png"
            if os.path.exists(thumb_path):
                try:
                    await asyncio.to_thread(os.remove, thumb_path)
                except:
                    pass
        
        # Cleanup ALL queued songs (including preloaded/cached ones)
        all_queued = await queue.get_queue(chat_id)
        if all_queued:
            for item in all_queued:
                # We keep the file in cache now
                # if item.file_path and os.path.exists(item.file_path):
                #     try:
                #         await asyncio.to_thread(os.remove, item.file_path)
                #         logger.info(f"Cleaned up cached file: {item.file_path}")
                #     except:
                #         pass
                # Cleanup thumbnail
                thumb_path = f"cache/{item.id}.png"
                if os.path.exists(thumb_path):
                    try:
                        await asyncio.to_thread(os.remove, thumb_path)
                    except:
                        pass

        try:
            await queue.clear(chat_id)
            await db.remove_call(chat_id)
        except:
            pass

        try:
            if client:
                await client.leave_call(chat_id, close=False)
        except:
            pass
        
        # Clear connection cache
        if chat_id in self._connection_cache:
            del self._connection_cache[chat_id]

    # Track active preload tasks per chat
    _preload_tasks: dict[int, asyncio.Task] = {}
    _preload_cancelled: set[int] = set()

    async def _start_watchdog(self, chat_id: int, duration_sec: int) -> None:
        """Start a watchdog timer to auto-skip if stream gets stuck."""
        # Cancel any existing watchdog for this chat
        if chat_id in self._watchdog_tasks:
            try:
                self._watchdog_tasks[chat_id].cancel()
            except:
                pass
        
        async def watchdog():
            try:
                # Wait for song duration + 60 second buffer
                buffer = 60
                await asyncio.sleep(duration_sec + buffer)
                
                # Check if still playing the same song (stuck state)
                media = await queue.get_current(chat_id)
                if media and await db.get_call(chat_id):
                    import time
                    played_at = getattr(media, 'played_at', 0)
                    elapsed = time.time() - played_at if played_at else 0
                    
                    # If elapsed time exceeds expected duration, stream is stuck
                    if elapsed >= duration_sec:
                        logger.warning(f"⚠️ Watchdog triggered for chat {chat_id} - stream stuck after {elapsed:.0f}s")
                        await self.play_next(chat_id)
            except asyncio.CancelledError:
                pass  # Normal cancellation when song changes
            except Exception as e:
                logger.error(f"Watchdog error for {chat_id}: {e}")
            finally:
                if chat_id in self._watchdog_tasks:
                    del self._watchdog_tasks[chat_id]
        
        self._watchdog_tasks[chat_id] = asyncio.create_task(watchdog())


    def _cancel_watchdog(self, chat_id: int) -> None:
        """Cancel watchdog timer for a chat."""
        if chat_id in self._watchdog_tasks:
            try:
                self._watchdog_tasks[chat_id].cancel()
                del self._watchdog_tasks[chat_id]
            except:
                pass


    async def _start_unmute_keeper(self, chat_id: int) -> None:
        """Start a periodic unmute keeper to prevent auto-mute during long sessions."""
        # Cancel any existing unmute keeper for this chat
        if chat_id in self._unmute_keeper_tasks:
            try:
                self._unmute_keeper_tasks[chat_id].cancel()
            except:
                pass
        
        async def unmute_keeper():
            counter = 0
            try:
                while True:
                    # Wait 60 seconds between checks (Reduced frequency to prevent FloodWait)
                    await asyncio.sleep(60)
                    counter += 1
                    
                    # Check if still actively playing
                    if not await db.get_call(chat_id):
                        break  # Not in call anymore, stop keeper
                    
                    # Check if paused - skip unmute/connection checks while paused
                    is_playing = await db.playing(chat_id)
                    if not is_playing:
                        logger.debug(f"Unmute keeper: chat {chat_id} is paused, skipping")
                        continue

                    try:
                        client = await db.get_assistant(chat_id)

                        # CONNECTION CHECK
                        # Check if assistant is actually in the call
                        try:
                            # logger.info(f"Checking assistant connection in chat {chat_id}...")
                            in_call = await self._is_assistant_in_vc(chat_id, client)
                            
                            if in_call:
                                # logger.debug(f"✓ Assistant is in VC for chat {chat_id}")
                                pass
                            else:
                                logger.warning(f"⚠️ Assistant missing from VC in chat {chat_id}, forcing rejoin...")
                                # Enforce a 90-second cooldown between rejoins to avoid FloodWait
                                import time as _time
                                last = self._last_rejoin.get(chat_id, 0)
                                if _time.time() - last < 90:
                                    logger.warning(f"Rejoin cooldown active for {chat_id}, skipping...")
                                else:
                                    # Force rejoin
                                    try:
                                        # Clear cache so next check is real
                                        if chat_id in self._connection_cache:
                                            del self._connection_cache[chat_id]

                                        media = await queue.get_current(chat_id)
                                        if media:
                                            # Leave first to clean up state
                                            try:
                                                await client.leave_group_call(chat_id)
                                                await asyncio.sleep(3)
                                            except Exception as e:
                                                logger.debug(f"Leave call failed (expected): {e}")

                                            # Use client.play() so FloodWait is handled
                                            from pytgcalls import types as _types
                                            stream = _types.MediaStream(
                                                media_path=media.file_path,
                                                audio_parameters=_types.AudioQuality.MEDIUM,
                                                video_parameters=_types.VideoQuality.HD_720p,
                                                audio_flags=_types.MediaStream.Flags.AUTO_DETECT,
                                                video_flags=_types.MediaStream.Flags.IGNORE,
                                            )
                                            try:
                                                await client.play(
                                                    chat_id=chat_id,
                                                    stream=stream,
                                                    config=_types.GroupCallConfig(auto_start=False),
                                                )
                                            except Exception as play_err:
                                                if "FLOOD_WAIT" in str(play_err) or "420" in str(play_err):
                                                    import re as _re
                                                    wait_time = 30
                                                    m = _re.search(r"wait\s+(\d+)\s+seconds", str(play_err))
                                                    if m:
                                                        wait_time = int(m.group(1)) + 5
                                                    logger.warning(f"FloodWait during rejoin, sleeping {wait_time}s")
                                                    await asyncio.sleep(wait_time)
                                                    # Retry once after waiting
                                                    await client.play(
                                                        chat_id=chat_id,
                                                        stream=stream,
                                                        config=_types.GroupCallConfig(auto_start=False),
                                                    )
                                                else:
                                                    raise play_err

                                            self._last_rejoin[chat_id] = _time.time()
                                            logger.info(f"✅ Successfully rejoined VC in chat {chat_id}")
                                            await asyncio.sleep(2)
                                            continue  # Skip unmute toggles this loop
                                    except Exception as e:
                                        logger.error(f"Failed to auto-rejoin VC in {chat_id}: {e}")
                        except Exception as e:
                            logger.error(f"Connection check failed for {chat_id}: {e}")

                        # Only unmute/resume if actively playing (not paused)
                        # Double-check pause state before resuming
                        current_state = await db.playing(chat_id)
                        if current_state:  # Only if still playing
                            # Explicitly mute then unmute to force state update
                            # This helps when Telegram auto-mutes the participant
                            try:
                                await client.mute_stream(chat_id)
                                await asyncio.sleep(0.5)
                                await client.unmute_stream(chat_id)
                                # logger.debug(f"Unmute keeper: toggled mute/unmute for chat {chat_id}")
                            except AttributeError:
                                # Fallback for older pytgcalls versions
                                await client.resume(chat_id)
                                # logger.debug(f"Unmute keeper: called resume for chat {chat_id}")
                    except Exception as e:
                        logger.debug(f"Unmute keeper check failed for {chat_id}: {e}")
                        
            except asyncio.CancelledError:
                pass  # Normal cancellation when playback stops
            except Exception as e:
                logger.error(f"Unmute keeper error for {chat_id}: {e}")
            finally:
                if chat_id in self._unmute_keeper_tasks:
                    del self._unmute_keeper_tasks[chat_id]
        
        self._unmute_keeper_tasks[chat_id] = asyncio.create_task(unmute_keeper())
        logger.info(f"Started unmute keeper for chat {chat_id}")

    async def _is_assistant_in_vc(self, chat_id: int, client) -> bool:
        """Check if assistant is physically present in the Telegram group call."""
        import time
        
        # 1. Check Cache
        if chat_id in self._connection_cache:
            last_checked = self._connection_cache[chat_id]
            # Valid for 5 minutes (300s)
            if (time.time() - last_checked) < 300:
                return True
        
        try:
            # Get Userbot client (Pyrogram)
            # Fix: db.get_assistant returns PyTgCalls object, which may not have .name
            # Fetch name from DB cache which is populated by get_assistant
            session_name = db.assistant.get(chat_id)
            if not session_name:
                # Should not happen if get_assistant was called, but safety fallback
                logger.warning(f"Session name not found in cache for {chat_id}")
                return True 
                
            ub = await userbot.get_client_by_name(session_name)
            
            # Resolve peer and find call
            peer = await ub.resolve_peer(chat_id)
            if hasattr(peer, 'channel_id'):
                full_chat = await ub.invoke(functions.channels.GetFullChannel(channel=peer))
            else:
                full_chat = await ub.invoke(functions.messages.GetFullChat(chat_id=peer.chat_id))
            
            if not full_chat.full_chat.call:
                logger.debug(f"Connection Check: No active call found in chat {chat_id}")
                return False # No call exists
                
            # Check participants
            results = await ub.invoke(
                functions.phone.GetGroupParticipants(
                    call=full_chat.full_chat.call,
                    ids=[],
                    sources=[],
                    offset="",
                    limit=100
                )
            )
            
            # Check if self (assistant) is in list
            my_id = ub.me.id
            for p in results.participants:
                if p.peer.user_id == my_id:
                    # Update Cache
                    self._connection_cache[chat_id] = time.time()
                    return True
            
            logger.debug(f"Connection Check: Assistant {my_id} NOT found in participants list")
            return False
            
        except Exception as e:
            err_str = str(e)
            from pyrogram.errors import AuthKeyUnregistered
            from bot import userbot
            if isinstance(e, AuthKeyUnregistered) or "401 AUTH_KEY_UNREGISTERED" in err_str:
                logger.error(f"Connection check detected unregistered userbot client: {e}")
                if 'session_name' in locals() and session_name:
                    await db.remove_session(session_name)
                    await userbot.remove_client(session_name)
                return False
                
            if "FLOOD_WAIT" in err_str:
                logger.warning(f"FloodWait during connection check for {chat_id}: {e}")
                # Assume True to avoid compounding the flood wait
                return True
            
            logger.error(f"Failed to check participant status in {chat_id}: {e}")
            # If we get a specific error like 'GROUPCALL_FORBIDDEN', return False effectively
            if "GROUPCALL_FORBIDDEN" in err_str or "CHANNEL_INVALID" in err_str:
                 return False
            # Otherwise assume True to avoid loops
            return True

    def _cancel_unmute_keeper(self, chat_id: int) -> None:
        """Cancel unmute keeper for a chat."""
        if chat_id in self._unmute_keeper_tasks:
            try:
                self._unmute_keeper_tasks[chat_id].cancel()
                del self._unmute_keeper_tasks[chat_id]
                logger.info(f"Stopped unmute keeper for chat {chat_id}")
            except:
                pass

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
            if config.ENABLE_DIRECT_STREAMING and not next_track.url.startswith("t.me") and not next_track.video:
                # Direct streaming for YouTube/external URLs (Audio Only)
                quality = await db.get_quality(chat_id)
                next_track.file_path = await yt.get_stream_url(next_track.id, video=next_track.video, quality=quality)
                if not next_track.file_path:
                    logger.warning(f"Stream URL extraction failed, falling back to download")
                    next_track.file_path = await yt.download(next_track.id, video=next_track.video)
            else:
                # Download for Telegram files or if streaming disabled
                next_track.file_path = await yt.download(next_track.id, video=next_track.video)
            
            # Check if cancelled after download (cleanup if needed)
                self._preload_cancelled.discard(chat_id)
                if next_track.file_path and os.path.exists(next_track.file_path):
                    try:
                        await asyncio.to_thread(os.remove, next_track.file_path)
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
            if await db.get_call(chat_id) and not await queue.get_next(chat_id, check=True):
                await queue.add(chat_id, next_track)
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
            # 1. Try Direct Streaming (if enabled) - Audio Only
            if config.ENABLE_DIRECT_STREAMING and track.req_type != "telegram" and not track.url.startswith("t.me") and not track.video:
                quality = await db.get_quality(chat_id)
                track.file_path = await yt.get_stream_url(track.id, video=track.video, quality=quality)
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
        audio_stream_index: int = 0,
        video_stream_index: int = 0,
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

        # Check if local cached file is missing from disk
        if not media.file_path.startswith("http") and not os.path.exists(media.file_path):
            logger.warning(f"Cached local file {media.file_path} is missing! Cleaning DB metadata and redownloading...")
            try:
                # Remove stale cache record from database so that download runs fresh
                await db.cache_metadata.delete_one({"_id": media.id})
                # Attempt download again
                media.file_path = await yt.download(media.id, video=media.video)
            except Exception as e:
                logger.error(f"Failed to redownload missing cached file: {e}")
                media.file_path = None

            if not media.file_path or not os.path.exists(media.file_path):
                await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
                return await self.play_next(chat_id)

        # Build ffmpeg parameters
        ffmpeg_params = f"-ss {seek_time}" if seek_time > 1 else None
        
        if media.file_path.startswith("http"):
             # reconnect flags + increased analyze duration for better probing
             net_flags = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 15000000 -probesize 100000000"
             ffmpeg_params = f"{net_flags} {ffmpeg_params}" if ffmpeg_params else net_flags
        
        # Audio Stream Selection
        # If specific audio index requested (and not default 0)
        if audio_stream_index > 0:
             # -map 0:a:<index> selects the Nth audio stream
             # We also map video 0:v:0 to ensure we keep video
             map_flags = f"-map 0:v:{video_stream_index} -map 0:a:{audio_stream_index}"
             ffmpeg_params = f"{ffmpeg_params} {map_flags}" if ffmpeg_params else map_flags
             logger.info(f"Using custom stream map: {map_flags}")
        
        # Add User-Agent and other headers for network streams to improve probing reliability
        if media.file_path.startswith("http"):
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            header_params = f'-headers "User-Agent: {user_agent}\r\n"'
            ffmpeg_params = f"{ffmpeg_params} {header_params}" if ffmpeg_params else header_params
        
        # Audio Quality Selection
        quality_setting = await db.get_quality(chat_id)
        if quality_setting == "low":
            audio_quality = types.AudioQuality.LOW
        elif quality_setting == "high":
            audio_quality = types.AudioQuality.HIGH
        elif quality_setting == "studio":
            audio_quality = types.AudioQuality.STUDIO
        else: # Medium/Default
            audio_quality = types.AudioQuality.MEDIUM

        logger.info(f"Using Audio Quality: {quality_setting.upper()}")



        stream = types.MediaStream(
            media_path=media.file_path,
            audio_parameters=audio_quality,
            video_parameters=types.VideoQuality.HD_720p,
            audio_flags=(
                types.MediaStream.Flags.AUTO_DETECT
                if media.video
                else types.MediaStream.Flags.REQUIRED
            ),
            video_flags=(
                types.MediaStream.Flags.AUTO_DETECT
                if media.video
                else types.MediaStream.Flags.IGNORE
            ),
            ffmpeg_parameters=ffmpeg_params,
        )
        try:
            try:
                await client.play(
                    chat_id=chat_id,
                    stream=stream,
                    config=types.GroupCallConfig(auto_start=False),
                )
            except Exception as e:
                # Handle FloodWait (Telegram Rate Limits)
                if "FLOOD_WAIT" in str(e) or "420" in str(e):
                    import re
                    wait_time = 10  # Default
                    try:
                        # Extract wait time from error message
                        match = re.search(r"wait\s+(\d+)\s+seconds", str(e))
                        if match:
                            wait_time = int(match.group(1)) + 2
                    except:
                        pass
                    
                    logger.warning(f"Got FloodWait during play(), sleeping for {wait_time}s and retrying...")
                    await asyncio.sleep(wait_time)
                    # Retry once
                    await client.play(
                        chat_id=chat_id,
                        stream=stream,
                        config=types.GroupCallConfig(auto_start=False),
                    )
                
                # Handle TimeoutError (FFmpeg/Network slow)
                elif "TimeoutError" in str(e) or "cancelled" in str(e).lower():
                    logger.warning(f"Got TimeoutError/Cancelled on play(), retrying with simple stream...")
                    # Retry (maybe recreating stream object helps?)
                    # For now just simply retry
                    await asyncio.sleep(1)
                    await client.play(
                        chat_id=chat_id,
                        stream=stream,
                        config=types.GroupCallConfig(auto_start=False),
                    )
                else:
                    raise e
                    
            # Force unpause and update DB status
            await client.resume(chat_id)
            await db.playing(chat_id, paused=False)
            if not seek_time:
                media.time = 0
                import time
                media.played_at = time.time()
                await queue.update_current(chat_id, media)

                await db.add_call(chat_id)
                self._consecutive_failures[chat_id] = 0
                
                # Register track in cache metadata database
                await db.register_cache_play(media)
                
                # Start watchdog to auto-skip if stream gets stuck
                is_live = getattr(media, 'is_live', False) or media.duration == "🔴 LIVE"
                duration_sec = 0
                if not is_live:
                    try:
                        duration_sec = getattr(media, 'duration_sec', 0) or utils.to_seconds(media.duration)
                    except:
                        duration_sec = 0
                if duration_sec > 0:
                    await self._start_watchdog(chat_id, duration_sec)
                
                # Start unmute keeper to prevent Telegram auto-mute during long sessions
                await self._start_unmute_keeper(chat_id)
                
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
                
                # Detect audio streams for track selector
                audio_track_count = 0
                try:
                    from bot.helpers._stream_info import get_audio_streams
                    logger.info(f"Checking audio streams for: {media.file_path}")
                    if media.file_path and not media.file_path.startswith("http"):
                        audio_streams = await get_audio_streams(media.file_path)
                        audio_track_count = len(audio_streams)
                        logger.info(f"Detected {audio_track_count} audio stream(s): {audio_streams}")
                        # Store for later use in callbacks
                        if audio_track_count > 1:
                            media.audio_streams = audio_streams
                            await queue.update_current(chat_id, media)
                    else:
                        logger.info(f"Skipping audio detection - HTTP stream or no file_path")
                except Exception as e:
                    logger.error(f"Failed to detect audio streams: {e}", exc_info=True)
                
                # Generate progress bar
                try:
                    duration_sec = utils.to_seconds(media.duration)
                    timer = utils.make_progress_bar(0, duration_sec)
                except Exception as e:
                    timer = None
                
                keyboard = buttons.controls(chat_id, timer=timer, autoplay=autoplay_status, audio_tracks=audio_track_count)
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
                except Exception as e:
                    # If edit fails (wrong message type, deleted message, etc), send new photo
                    logger.debug(f"Failed to edit media, sending new photo: {e}")
                    media.message_id = (await app.send_photo(
                        chat_id=chat_id,
                        photo=_thumb,
                        caption=text,
                        reply_markup=keyboard,
                    )).id
                
                # IMPORTANT: Save the new/updated message_id to the queue/DB
                # This ensures future control interactions target the correct message
                await queue.update_current(chat_id, media)
                
                
                # Proactive autoplay preload - predict and download next song in background
                if autoplay_status and not await queue.get_next(chat_id, check=True):
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
            # Silence warning on first few attempts as bot has retry logic
            if self._consecutive_failures[chat_id] == 0:
                logger.info(f"Initial NoAudioSourceFound for {media.title} - attempting re-fetch/retry")
            else:
                logger.warning(f"NoAudioSourceFound for {media.title} (Attempt {self._consecutive_failures[chat_id] + 1})")
            
            # 1. Clean up corrupted file if local
            if media.file_path and not media.file_path.startswith("http") and os.path.exists(media.file_path):
                try:
                    os.remove(media.file_path)
                    logger.info(f"Deleted corrupted file: {media.file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete corrupted file: {e}")

            # 2. Check retry limit (prevent infinite loops)
            if self._consecutive_failures[chat_id] > 2:
                self._consecutive_failures[chat_id] = 0
                await message.edit_text(_lang["error_no_audio"])
                return await self.play_next(chat_id)
            
            # 3. Retry Logic
            self._consecutive_failures[chat_id] += 1
            from pyrogram.errors import MessageNotModified
            try:
                await message.edit_text("🔄 File corrupted, re-fetching...")
            except MessageNotModified:
                pass
            except Exception as e:
                logger.debug(f"Could not edit message for re-fetch: {e}")
            
            try:
                # Re-fetch media (Stream OR Download)
                # We reuse the logic from play_next/prepare roughly
                
                # Try direct stream if applicable
                if config.ENABLE_DIRECT_STREAMING and media.req_type != "telegram" and not media.url.startswith("t.me") and not media.video:
                     quality = await db.get_quality(chat_id)
                     media.file_path = await yt.get_stream_url(media.id, video=media.video, quality=quality)
                     if not media.file_path:
                         media.file_path = await yt.download(media.id, video=media.video)
                else:
                     # Fallback to download
                     media.file_path = await yt.download(media.id, video=media.video)
                
                if media.file_path:
                     # Recursive retry
                     return await self.play_media(chat_id, message, media, seek_time)
            except Exception as e:
                logger.error(f"Retry re-fetch failed: {e}")

            await message.edit_text(_lang["error_no_audio"])
            await self.play_next(chat_id)
        except (ConnectionNotFound, TelegramServerError):
            await self.stop(chat_id)
            await message.edit_text(_lang["error_tg_server"])
        except RTMPStreamingUnsupported:
            await self.stop(chat_id)
            await message.edit_text(_lang["error_rtmp"])
        except Exception as e:
            from pyrogram.errors import AuthKeyUnregistered
            from bot import userbot
            if isinstance(e, AuthKeyUnregistered) or "401 AUTH_KEY_UNREGISTERED" in str(e):
                logger.error(f"Play Media detected unregistered userbot client: {e}")
                session_name = db.assistant.get(chat_id)
                if session_name:
                    await db.remove_session(session_name)
                    await userbot.remove_client(session_name)
                try:
                    await message.edit_text("⚠️ **Assistant Session Expired!**\n\nThe assistant account has been logged out from Telegram. I have removed it from the database. Please add a new assistant using /login in my PM.")
                except:
                    pass
                return await self.stop(chat_id)

            logger.error(f"Play Media Error: {e}", exc_info=True)
            try:
                await message.edit_text(f"❌ Error: {e}")
            except:
                pass
            await self.play_next(chat_id)


    async def change_stream(self, chat_id: int, audio_index: int) -> bool:
        """
        Change the active audio stream (language) for the current playback.
        Restarting the stream at the current position.
        """
        if not await db.get_call(chat_id):
            return False
            
        media = await queue.get_current(chat_id)
        if not media:
            return False
            
        # Get current position
        # We can't get exact position from py-tgcalls easily, so we estimate
        import time
        played_at = getattr(media, 'played_at', 0)
        current_position = int(time.time() - played_at) if played_at else 0
        
        # Prevent restart from beginning if position is glitchy
        if current_position < 0: current_position = 0
            
        # Re-play with new index
        try:
            # Need to find the original message to edit
            # If we don't have it, we can't easily edit, but we can still play.
            # However, play_media expects a message.
            # We will use the stored message_id to fetch it if possible, 
            # otherwise we might fail UI updates but stream will work.
            message = None
            if media.message_id:
                try:
                    msgs = await app.get_messages(chat_id, [media.message_id])
                    if msgs: message = msgs[0]
                except:
                    pass
            
            if not message:
                # Create a temporary status message if original lost
                message = await app.send_message(chat_id, "🔄 Switching audio track...")
            
            logger.info(f"Switching audio stream to index {audio_index} at {current_position}s")
            await self.play_media(
                chat_id, 
                message, 
                media, 
                seek_time=current_position, 
                audio_stream_index=audio_index
            )
            return True
        except Exception as e:
            logger.error(f"Failed to change stream: {e}")
            return False


    async def replay(self, chat_id: int) -> None:
        if not await db.get_call(chat_id):
            return
            
        media = await queue.get_current(chat_id)
        _lang = await lang.get_lang(chat_id)
        
        # Delete the old player message if it exists
        if hasattr(media, 'message_id') and media.message_id:
            try:
                await app.delete_messages(chat_id=chat_id, message_ids=media.message_id)
            except:
                pass
        
        # Send a fresh status message
        msg = await app.send_message(chat_id=chat_id, text=_lang["play_again"])
        await self.play_media(chat_id, msg, media)




    async def play_next(self, chat_id: int) -> None:
        # Acquire lock to prevent race conditions (multiple stream_end events)
        if chat_id not in self._play_next_locks:
            self._play_next_locks[chat_id] = asyncio.Lock()
        
        # Try to acquire lock, skip if already processing
        if self._play_next_locks[chat_id].locked():
            logger.debug(f"play_next already running for {chat_id}, skipping duplicate call")
            return
        
        async with self._play_next_locks[chat_id]:
            # Check consecutive failures to prevent loops
            if self._consecutive_failures[chat_id] >= 3:
                logger.warning(f"Stopping playback loop in {chat_id} due to 3 consecutive failures")
                self._consecutive_failures[chat_id] = 0
                return await self.stop(chat_id)

        # Cleanup previous track
        old_media = await queue.get_playing(chat_id)
        if old_media:
            # Disable buttons on previous song message
            if hasattr(old_media, 'message_id') and old_media.message_id:
                try:
                    await app.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=old_media.message_id,
                        reply_markup=None
                    )
                except MessageNotModified:
                    pass
                except Exception as e:
                    logger.error(f"Failed to cleanup buttons for {old_media.title}: {e}")
            # We keep the file in cache now
            # if old_media.file_path and os.path.exists(old_media.file_path):
            #     try:
            #         await asyncio.to_thread(os.remove, old_media.file_path)
            #     except:
            #         pass
            
            # Cleanup thumbnail
            thumb_path = f"cache/{old_media.id}.png"
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass

        media = await queue.get_next(chat_id)
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
            # Everything else (Telegram files, playlists) = no autoplay
            if old_media:
                old_req_type = getattr(old_media, 'req_type', None)
                
                # Only allow autoplay for YouTube search, direct YouTube URLs, playlists, and previous autoplay tracks
                if old_req_type not in ['search', 'youtube', 'autoplay', 'playlist']:
                    logger.info(f"Skipping autoplay - req_type '{old_req_type}' not eligible for autoplay")
                    return await self.stop(chat_id)
                
                # Check if autoplay enabled
                mode = await db.get_autoplay(chat_id)
                new_track = None
                
                if not mode:
                    # Autoplay disabled - just stop
                    return await self.stop(chat_id)

                # Autoplay logic with TF-IDF smart mode
                new_track = await yt.smart_autoplay(mode, previous_track=old_media)
                
                # Check if user added a song while we were fetching autoplay
                # If yes, prioritize user song and discard/ignore the autoplay result
                if await queue.get_queue(chat_id):
                    logger.info(f"User added song during autoplay fetch in {chat_id} - Switching to user track")
                    # Clear cancelled flag so new download can proceed
                    yt.clear_cancelled(chat_id)
                    media = await queue.get_next(chat_id)
                elif new_track:
                    # Add to queue
                    await queue.add(chat_id, new_track)
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
        is_live = getattr(media, "is_live", False)
        if is_live:
            msg = await app.send_message(chat_id=chat_id, text="📡 Connecting to live stream...")
        elif config.ENABLE_DIRECT_STREAMING and media.req_type != "telegram" and not media.url.startswith("t.me") and not media.video:
            msg = await app.send_message(chat_id=chat_id, text="⏭️ Loading next track...")
        else:
            msg = await app.send_message(chat_id=chat_id, text=_lang["play_next"])
        
        # Download or get stream URL
        if media.req_type != "telegram":
            # Direct streaming for YouTube/external URLs (Audio Only)
            # We force download for video because Telegram streaming is unstable for video
            if is_live or (config.ENABLE_DIRECT_STREAMING and not media.url.startswith("t.me") and not media.video):
                # Direct streaming for YouTube/external URLs
                logger.info(f"🎵 Using direct streaming for: {media.title}")
                quality = await db.get_quality(chat_id)
                media.file_path = await yt.get_stream_url(media.id, video=media.video, quality=quality)
                if not media.file_path and not is_live:
                    logger.warning(f"Stream URL extraction failed, falling back to download")
                    media.file_path = await yt.download(media.id, video=media.video)
            else:
                # Download for Telegram files or if streaming disabled
                media.file_path = await yt.download(media.id, video=media.video)
            if not media.file_path:
                self._consecutive_failures[chat_id] += 1
                await self.stop(chat_id)
                return await msg.edit_text(
                    _lang["error_no_file"].format(config.SUPPORT_CHAT)
                )
            
            # Reset failures on success
            self._consecutive_failures[chat_id] = 0


        media.message_id = msg.id
        await queue.update_current(chat_id, media)
        
        # Prevent Zombie State: Force leave before playing new track
        # This ensures a fresh connection for every song, resolving "silent playback" issues
        if config.ENABLE_DIRECT_STREAMING: # Only needed for streaming/long sessions
            try:
                client = await db.get_assistant(chat_id)
                await client.leave_call(chat_id)
                await asyncio.sleep(2)
            except:
                pass
                
        await self.play_media(chat_id, msg, media)


    async def ping(self) -> float:
        pings = [client.ping for client in self.clients]
        return round(sum(pings) / len(pings), 2)


    async def decorators(self, client: PyTgCalls) -> None:
        """Register stream event handlers for a specific PyTgCalls client."""
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
        if not hasattr(self, "_client_map"):
            self._client_map = {}
        self._client_map[userbot_client.name] = client
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
        # Find the PyTgCalls client using the map
        if not hasattr(self, "_client_map"):
            self._client_map = {}
        tgcalls_client = self._client_map.get(userbot_client.name)
        
        if not tgcalls_client:
            # Fallback: legacy check just in case (though broken previously)
            return False
        
        # Stop the client
        try:
            await tgcalls_client.stop()
        except:
            pass

        # Remove from list and map
        if tgcalls_client in self.clients:
            self.clients.remove(tgcalls_client)
        
        if userbot_client.name in self._client_map:
            del self._client_map[userbot_client.name]
            
        logger.info(f"PyTgCalls client removed for {userbot_client.name}")
        return True

    async def boot(self) -> None:
        PyTgCallsSession.notice_displayed = True
        for ub in userbot.clients:
            await self.add_pytgcalls_client(ub)
        logger.info("PyTgCalls client(s) started.")
        
        # Restore sessions after boot
        asyncio.create_task(self.restore_sessions())

    async def restore_sessions(self) -> None:
        """
        Scan Redis for active sessions and restore playback after restart.
        """
        from bot import config
        if not config.RESTORE_ON_STARTUP:
            logger.info("Session Restoration: Disabled by config.")
            return

        logger.info("Session Restoration: Scanning for active sessions...")
        prefix = config.REDIS_PREFIX
        
        # Use SCAN to find keys preventing blocking
        pattern = f"{prefix}current:*"
        cursor = 0
        restored_count = 0
        
        try:
            while True:
                cursor, keys = await queue.rds.scan(cursor, match=pattern, count=100)
                
                for key in keys:
                    try:
                        # Extract chat_id from key "happybot:current:123456"
                        chat_id = int(key.split(":")[-1])
                        
                        # Check if session is valid (VC exists)
                        try:
                            client = await db.get_assistant(chat_id)
                        except:
                            # No assistant or error -> skip
                            continue
                            
                        # Get media data
                        media = await queue.get_current(chat_id)
                        if not media:
                            continue
                            
                        # Skip Telegram file restoration (often expired links or costly to re-download)
                        if getattr(media, 'req_type', None) == 'telegram':
                             logger.info(f"Session Restoration: Skipping Telegram file for chat {chat_id}")
                             await self.stop(chat_id)
                             continue

                        # Resume playback
                        logger.info(f"Session Restoration: Restoring chat {chat_id} - '{media.title}'")
                        
                        try:
                            # Re-join and play
                            # Use stored time if available, or 0
                            seek_time = media.time if hasattr(media, 'time') else 0
                            
                            # Add to active calls BEFORE playing to pass checks
                            await db.add_call(chat_id)
                            
                            # Force leave call to clear zombie/ghost state
                            try:
                                client = await db.get_assistant(chat_id)
                                await client.leave_call(chat_id)
                                await asyncio.sleep(2)
                            except:
                                pass
                            
                            # Need message object for UI updates. 
                            # We can't easily get the original message object, but play_media needs it to edit.
                            # We will try to fetch the message if message_id exists
                            msg = None
                            if media.message_id:
                                try:
                                    msg = await app.get_messages(chat_id, media.message_id)
                                except:
                                    pass
                            
                            if not msg:
                                # Create a fresh status message if original is lost
                                msg = await app.send_message(chat_id, "🔄 Restoring playback...")
                            
                            await self.play_media(chat_id, msg, media, seek_time=seek_time)
                            restored_count += 1
                            
                            # Add small delay to prevent floodwaits
                            await asyncio.sleep(2)
                            
                        except Exception as e:
                            logger.error(f"Session Restoration: Failed for {chat_id}: {e}")
                            await self.stop(chat_id)
                            
                    except Exception as e:
                        logger.error(f"Session Restoration: Key error {key}: {e}")
                
                if cursor == 0:
                    break
                    
            logger.info(f"Session Restoration: Completed. Restored {restored_count} sessions.")
            
        except Exception as e:
            logger.error(f"Session Restoration: Critical Fail: {e}")

