from pyrogram import filters, types

from bot import app, db, lang, queue
from bot.helpers import _admins, buttons


async def update_player_button(chat_id: int, autoplay_status):
    """Update the autoplay button in the currently playing song's message."""
    try:
        media = queue.get_current(chat_id)
        if media and media.message_id:
            keyboard = buttons.controls(chat_id, autoplay=autoplay_status)
            await app.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=media.message_id,
                reply_markup=keyboard
            )
    except:
        pass


@app.on_message(filters.command("autoplay") & filters.group & ~app.bl_users)
@lang.language()
@_admins.can_manage_vc
async def autoplay_cmd(_, m: types.Message):
    genres = [
        "pop", "rock", "hiphop", "electronic", "jazz", "classical", "metal", 
        "country", "rnb", "indie", "latin", "kpop", "anime", "lofi", 
        "blues", "reggae", "disco", "punk", "ambient", "random"
    ]
    usage = f"<b>Usage:</b>\n/autoplay [on|smart|off]\n<b>Genres:</b> {', '.join(genres)}"
    
    if len(m.command) != 2:
        return await m.reply_text(usage)

    state = m.command[1].lower()
    new_status = None
    
    if state in ["on", "smart"]:
        new_status = "smart"
        await db.set_autoplay(m.chat.id, new_status)
        await m.reply_text("<b>Smart Autoplay enabled.</b> I will try to predict the next song!")
    elif state == "off":
        new_status = False
        await db.set_autoplay(m.chat.id, new_status)
        await m.reply_text("<b>Autoplay disabled.</b>")
    elif state in genres:
        new_status = state
        await db.set_autoplay(m.chat.id, new_status)
        await m.reply_text(f"<b>Autoplay set to: {state.capitalize()}</b>")
    else:
        return await m.reply_text(usage)
    
    # Update the inline button in the player if a song is playing
    if new_status is not None:
        await update_player_button(m.chat.id, new_status)
