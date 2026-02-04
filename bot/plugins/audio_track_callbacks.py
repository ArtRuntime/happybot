# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

from pyrogram import filters, types
from bot import anon, app, db, logger, queue
from bot.helpers import buttons, can_manage_vc

@app.on_callback_query(filters.regex("audio_menu ") & ~app.bl_users)
@can_manage_vc
async def audio_menu_handler(_, query: types.CallbackQuery):
    """Show audio track selection menu"""
    chat_id = int(query.data.split()[1])
    
    if not await db.get_call(chat_id):
        return await query.answer("❌ No active playback.", show_alert=True)
    
    # Get current media and audio streams
    media = await queue.get_current(chat_id)
    if not media:
        return await query.answer("❌ No media playing.", show_alert=True)
    
    # Get stored audio streams
    audio_streams = getattr(media, 'audio_streams', [])
    
    if not audio_streams or len(audio_streams) <= 1:
        return await query.answer("ℹ️ Only one audio track available.", show_alert=True)
    
    # Get current audio index (default to 0)
    current_index = getattr(media, 'current_audio_index', 0)
    
    # Show menu
    keyboard = buttons.audio_track_menu(chat_id, audio_streams, current_index)
    await query.edit_message_reply_markup(reply_markup=keyboard)


@app.on_callback_query(filters.regex("audio_select ") & ~app.bl_users)
@can_manage_vc
async def audio_select_handler(_, query: types.CallbackQuery):
    """Handle audio track selection"""
    args = query.data.split()
    chat_id = int(args[1])
    audio_index = int(args[2])
    
    if not await db.get_call(chat_id):
        return await query.answer("❌ No active playback.", show_alert=True)
    
    await query.answer(f"🔄 Switching to Track {audio_index + 1}...", show_alert=True)
    
    # Switch audio stream
    success = await anon.change_stream(chat_id, audio_index)
    
    if success:
        # Update stored index
        media = await queue.get_current(chat_id)
        if media:
            media.current_audio_index = audio_index
            await queue.update_current(chat_id, media)
        
        # Update menu to show new selection
        audio_streams = getattr(media, 'audio_streams', [])
        if audio_streams:
            keyboard = buttons.audio_track_menu(chat_id, audio_streams, audio_index)
            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except:
                pass
    else:
        await query.answer("❌ Failed to switch track.", show_alert=True)


@app.on_callback_query(filters.regex("audio_menu_close") & ~app.bl_users)
async def audio_menu_close_handler(_, query: types.CallbackQuery):
    """Close audio menu and restore player controls"""
    # Extract chat_id from message
    # We need to restore the original controls
    try:
        # Get chat_id from the callback message
        chat_id = query.message.chat.id
        
        # Get current media
        media = await queue.get_current(chat_id)
        if not media:
            return await query.answer()
        
        # Restore player controls
        autoplay_status = await db.get_autoplay(chat_id)
        audio_streams = getattr(media, 'audio_streams', [])
        audio_track_count = len(audio_streams) if audio_streams else 0
        
        keyboard = buttons.controls(chat_id, autoplay=autoplay_status, audio_tracks=audio_track_count)
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error closing audio menu: {e}")
        await query.answer()


@app.on_callback_query(filters.regex("audio_menu_info") & ~app.bl_users)
async def audio_menu_info_handler(_, query: types.CallbackQuery):
    """Info button - just acknowledge"""
    await query.answer("Select an audio track to switch language/audio.", show_alert=False)
