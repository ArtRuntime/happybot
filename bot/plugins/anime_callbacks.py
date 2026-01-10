# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types
from pyrogram.types import InputMediaPhoto

from bot import anime, anon, app, db, logger, queue
from bot.helpers import buttons, Media, Track, thumb
from bot.plugins.anime_plugin import anime_cache, get_cache


@app.on_callback_query(filters.regex("^anime_"))
async def anime_callbacks(_, query: types.CallbackQuery):
    """Handle all anime-related callbacks."""
    try:
        data = query.data
        chat_id = query.message.chat.id
        
        # Close button
        if data == "anime_close":
            await query.message.delete()
            return
        
        # Search result pagination
        if data.startswith("anime_pg "):
            parts = data.split()
            page_chat_id, page = int(parts[1]), int(parts[2])
            cache = get_cache(page_chat_id)
            results = cache.get("search", [])
            keyboard = buttons.anime_search_results(results, page_chat_id, page)
            await query.message.edit_reply_markup(reply_markup=keyboard)
            await query.answer()
            return
        
        # Anime selected from search results
        if data.startswith("anime_sel "):
            parts = data.split()
            sel_chat_id, idx = int(parts[1]), int(parts[2])
            cache = get_cache(sel_chat_id)
            anime_id = cache["anime"].get(str(idx))
            if anime_id:
                await handle_anime_select(query, anime_id)
            else:
                await query.answer("❌ Session expired, search again", show_alert=True)
            return
        
        # Episode list requested
        elif data.startswith("anime_ep_list "):
            anime_id = data.split(maxsplit=1)[1]
            await show_episode_list(query, anime_id)
        
        # Episode selected
        elif data.startswith("anime_ep "):
            parts = data.split()
            if len(parts) >= 3:
                anime_id, ep_id = parts[1], parts[2]
                await handle_episode_select(query, anime_id, ep_id)
        
        # Episode pagination
        elif data.startswith("anime_ep_page "):
            parts = data.split()
            anime_id, page = parts[1], int(parts[2])
            await show_episode_list(query, anime_id, page)
        
        # Server selector
        elif data.startswith("anime_server "):
            parts = data.split()
            anime_id, ep_id = parts[1], parts[2]
            await show_server_selector(query, anime_id, ep_id)
        
        # Server selected
        elif data.startswith("anime_use_server "):
            parts = data.split()
            anime_id, ep_id, server, stream_type = parts[1], parts[2], parts[3], parts[4]
            await start_anime_stream(query, anime_id, ep_id, server, stream_type)
        
        # Sub/Dub toggle
        elif data.startswith("anime_type "):
            parts = data.split()
            anime_id, ep_id, current_server = parts[1], parts[2], parts[3]
            # Toggle between sub and dub
            current_type = "sub"  # Get from queue metadata
            new_type = "dub" if current_type == "sub" else "sub"
            await start_anime_stream(query, anime_id, ep_id, current_server, new_type)
        
        # Playback controls
        elif data.startswith("anime_pause "):
            chat_id = int(data.split()[1])
            await anon.pause(chat_id)
            await query.answer("⏸ Paused", show_alert=False)
        
        elif data.startswith("anime_resume "):
            chat_id = int(data.split()[1])
            await anon.resume(chat_id)
            await query.answer("▶️ Resumed", show_alert=False)
        
        elif data.startswith("anime_skip "):
            chat_id = int(data.split()[1])
            await anon.skip(chat_id)
            await query.answer("⏭ Skipped", show_alert=False)
        
        elif data.startswith("anime_stop "):
            chat_id = int(data.split()[1])
            await anon.stop(chat_id)
            await query.answer("⏹ Stopped", show_alert=False)
            try:
                await query.message.delete()
            except:
                pass
    
    except Exception as e:
        logger.error(f"Anime callback error: {e}", exc_info=True)
        await query.answer("❌ An error occurred", show_alert=True)


async def handle_anime_select(query: types.CallbackQuery, anime_id: str):
    """Handle anime selection from search results."""
    await query.answer("Loading anime info...")
    
    try:
        chat_id = query.message.chat.id
        cache = get_cache(chat_id)
        
        info = await anime.get_anime_info(anime_id)
        if not info:
            return await query.answer("❌ Failed to load anime info", show_alert=True)
        
        data = info.get("data", {})
        title = data.get("title", "Unknown")
        japanese_title = data.get("japanese_title", "")
        poster = data.get("poster", "")
        show_type = data.get("showType", "")
        anime_info = data.get("animeInfo", {})
        overview = anime_info.get("Overview", "No description available")
        
        # Get episodes
        episodes_data = await anime.get_episodes(anime_id)
        if episodes_data:
            episodes = episodes_data.get("episodes", [])
            cache["episodes"][anime_id] = episodes
            total_eps = episodes_data.get("totalEpisodes", len(episodes))
        else:
            total_eps = "?"
        
        caption = (
            f"📺 **{title}**\n"
            f"🇯🇵 {japanese_title}\n"
            f"🎬 Type: {show_type}\n"
            f"📊 Episodes: {total_eps}\n\n"
            f"📝 {overview[:200]}{'...' if len(overview) > 200 else ''}"
        )
        
        keyboard = buttons.anime_episode_selector(anime_id, episodes, 0)
        
        if poster:
            try:
                await query.message.edit_media(
                    InputMediaPhoto(media=poster, caption=caption),
                    reply_markup=keyboard
                )
            except:
                await query.message.edit_text(caption, reply_markup=keyboard)
        else:
            await query.message.edit_text(caption, reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Failed to handle anime select: {e}", exc_info=True)
        await query.answer("❌ Error loading anime", show_alert=True)


async def show_episode_list(query: types.CallbackQuery, anime_id: str, page: int = 0):
    """Show episode list with pagination."""
    await query.answer()
    
    chat_id = query.message.chat.id
    cache = get_cache(chat_id)
    
    episodes = cache["episodes"].get(anime_id, [])
    if not episodes:
        # Fetch if not cached
        episodes_data = await anime.get_episodes(anime_id)
        if episodes_data:
            episodes = episodes_data.get("episodes", [])
            cache["episodes"][anime_id] = episodes
    
    if not episodes:
        return await query.answer("❌ No episodes found", show_alert=True)
    
    keyboard = buttons.anime_episode_selector(anime_id, episodes, page)
    
    try:
        await query.message.edit_reply_markup(reply_markup=keyboard)
    except:
        pass


async def handle_episode_select(query: types.CallbackQuery, anime_id: str, ep_id: str):
    """Handle episode selection - show server options."""
    await show_server_selector(query, anime_id, ep_id, stream_type="sub")


async def show_server_selector(query: types.CallbackQuery, anime_id: str, ep_id: str, stream_type: str = "sub"):
    """Show available servers for the episode."""
    await query.answer("Loading servers...")
    
    try:
        stream_data = await anime.get_stream(anime_id, ep_id, "hd-1", stream_type)
        if not stream_data:
            return await query.answer("❌ No streams available", show_alert=True)
        
        servers = stream_data.get("servers", [])
        if not servers:
            return await query.answer("❌ No servers found", show_alert=True)
        
        keyboard = buttons.anime_server_selector(anime_id, ep_id, servers, stream_type)
        
        await query.message.edit_reply_markup(reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Failed to load servers: {e}", exc_info=True)
        await query.answer("❌ Error loading servers", show_alert=True)


async def start_anime_stream(
    query: types.CallbackQuery,
    anime_id: str,
    ep_id: str,
    server: str,
    stream_type: str
):
    """Start streaming the anime episode."""
    await query.answer("Starting stream...")
    
    chat_id = query.message.chat.id
    
    try:
        # Get stream URL
        stream_data = await anime.get_stream(anime_id, ep_id, server, stream_type)
        if not stream_data:
            return await query.answer("❌ Failed to get stream", show_alert=True)
        
        streaming_links = stream_data.get("streamingLink", [])
        if not streaming_links:
            return await query.answer("❌ No streaming link available", show_alert=True)
        
        # Get the m3u8/mp4 link
        link_data = streaming_links[0].get("link", {})
        stream_url = link_data.get("file")
        
        if not stream_url:
            return await query.answer("❌ Invalid stream URL", show_alert=True)
        
        # Get anime and episode info
        info = await anime.get_anime_info(anime_id)
        data = info.get("data", {}) if info else {}
        title = data.get("title", "Unknown Anime")
        poster = data.get("poster", "")
        
        # Find episode details
        cache = get_cache(chat_id)
        episodes = cache["episodes"].get(anime_id, [])
        ep_title = f"Episode {ep_id}"
        for ep in episodes:
            if str(ep.get("data_id")) == str(ep_id):
                ep_title = f"Episode {ep.get('episode_no', '?')} - {ep.get('title', '')}"
                break
        
        # Create track object
        track = Track(
            title=f"{title} - {ep_title}",
            link=stream_url,
            thumb=poster if poster else await thumb.gen_thumb(),
            dur=0,  # Duration unknown for anime
            req_by=query.from_user.id,
            video=True  # Anime is video
        )
        
        # Add to queue and play
        media = Media(
            chat_id=chat_id,
            message_id=query.message.id,
            track=track
        )
        
        await queue.add(chat_id, track)
        
        if await db.get_call(chat_id):
            # Already playing something, this will queue
            await query.answer("✅ Added to queue", show_alert=False)
        else:
            # Start playback
            await anon.start_stream(chat_id, media)
            
            # Update message with playback controls
            keyboard = buttons.anime_controls(
                chat_id,
                anime_id,
                ep_id,
                server,
                stream_type
            )
            
            caption = (
                f"▶️ **Now Streaming**\n\n"
                f"📺 {title}\n"
                f"🎬 {ep_title}\n"
                f"🌐 Server: {server.upper()}\n"
                f"🗣 Type: {stream_type.upper()}\n"
                f"👤 Requested by: {query.from_user.mention}"
            )
            
            try:
                await query.message.edit_caption(caption, reply_markup=keyboard)
            except:
                await query.message.edit_text(caption, reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Failed to start anime stream: {e}", exc_info=True)
        await query.answer("❌ Failed to start stream", show_alert=True)
