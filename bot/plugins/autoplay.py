from pyrogram import filters, types

from bot import app, db, lang
from bot.helpers import _admins


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
    
    if state in ["on", "smart"]:
        await db.set_autoplay(m.chat.id, "smart")
        await m.reply_text("<b>Smart Autoplay enabled.</b> I will try to predict the next song!")
    elif state == "off":
        await db.set_autoplay(m.chat.id, False)
        await m.reply_text("<b>Autoplay disabled.</b>")
    elif state in genres:
        await db.set_autoplay(m.chat.id, state)
        await m.reply_text(f"<b>Autoplay set to: {state.capitalize()}</b>")
    else:
        await m.reply_text(usage)
