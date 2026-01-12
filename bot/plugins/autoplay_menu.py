# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

from pyrogram import filters, types, errors

from bot import app, db, lang, queue
from bot.helpers import buttons, utils


# Autoplay menu callbacks
@app.on_callback_query(filters.regex("autoplay_set") & ~app.bl_users)
@lang.language()
async def _autoplay_set(_, query: types.CallbackQuery):
    args = query.data.split()
    chat_id, mode = int(args[1]), args[2]
    
    # Set autoplay mode
    if mode == "off":
        await db.set_autoplay(chat_id, False)
        status = "OFF ❌"
    else:
        await db.set_autoplay(chat_id, mode)
        status = f"ON - {mode.upper()} ✅"
    
    await query.answer(f"Autoplay: {status}", show_alert=False)
    
    # Update menu to show current selection
    keyboard = buttons.autoplay_menu(chat_id, mode if mode != "off" else False)
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except errors.MessageNotModified:
        pass


@app.on_callback_query(filters.regex("autoplay_close") & ~app.bl_users)
async def _autoplay_close(_, query: types.CallbackQuery):
    # Get current playing info to restore controls
    chat_id = query.message.chat.id
    current = queue.get_current(chat_id)
    
    if current:
        autoplay_status = await db.get_autoplay(chat_id)
        
        # Restore progress bar
        try:
            played = getattr(current, 'time', 0)
            duration = getattr(current, 'duration_sec', 0)
            if duration > 0:
                timer = utils.make_progress_bar(played, duration)
            else:
                timer = None
        except:
            timer = None
            
        keyboard = buttons.controls(chat_id, timer=timer, autoplay=autoplay_status)
        await query.edit_message_reply_markup(reply_markup=keyboard)
    else:
        # If nothing playing, show stopped state instead of deleting
        autoplay_status = await db.get_autoplay(chat_id)
        keyboard = buttons.controls(chat_id, status="Stopped 🛑", autoplay=autoplay_status, remove=True)
        await query.edit_message_reply_markup(reply_markup=keyboard)
