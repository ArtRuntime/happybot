from pyrogram import filters, types
from bot import app, db

@app.on_message(filters.command("autoleave"))
async def toggle_auto_leave(_, message: types.Message):
    """Toggle auto-leave for current chat. Sudo only."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    
    # Restrict to sudo users only
    if user_id not in app.sudoers:
        await message.reply_text(
            "🔒 **Access Denied**\n\n"
            "This command is restricted to bot administrators only."
        )
        return
    
    chat_id = message.chat.id
    
    # Get current status
    current_status = await db.get_auto_leave_enabled(chat_id)
    
    # Toggle status
    new_status = not current_status
    await db.set_auto_leave_enabled(chat_id, new_status)
    
    status_emoji = "✅" if new_status else "❌"
    status_text = "Enabled" if new_status else "Disabled"
    
    await message.reply_text(
        f"{status_emoji} **Auto-Leave {status_text}**\n\n"
        f"**Chat:** {message.chat.title or 'This Chat'}\n"
        f"**Status:** {status_text}\n\n"
        + (
            "⚠️ The assistant will automatically leave this chat when inactive."
            if new_status
            else "🔒 The assistant will stay in this chat even when inactive."
        )
    )
