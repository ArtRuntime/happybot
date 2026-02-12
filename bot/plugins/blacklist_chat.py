import re
from datetime import datetime, timedelta
from pyrogram import filters
from pyrogram.types import ChatPermissions
from pyrogram.enums import ChatMemberStatus

from bot import app, config, db
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Blacklist"
__HELP__ = """
**Blacklist Commands:**

/blacklisted - Get All The Blacklisted Words In The Chat.
/blacklist [WORD|SENTENCE] - Blacklist A Word Or A Sentence.
/whitelist [WORD|SENTENCE] - Whitelist A Word Or A Sentence.
"""

@app.on_message(filters.command("blacklist") & filters.group)
@capture_err
async def save_filters(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/blacklist [WORD|SENTENCE]")
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check Admin
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    word = message.text.split(None, 1)[1].strip()
    if not word:
        return await message.reply_text("**Usage**\n__/blacklist [WORD|SENTENCE]__")
        
    await db.add_chat_filter(chat_id, word)
    await message.reply_text(f"__**Blacklisted {word}.**__")


@app.on_message(filters.command("blacklisted") & filters.group)
@capture_err
async def get_filterss(_, message):
    data = await db.get_chat_filters(message.chat.id)
    if not data:
        await message.reply_text("**No blacklisted words in this chat.**")
    else:
        msg = f"List of blacklisted words in {message.chat.title} :\n"
        for word in data:
            msg += f"**-** `{word}`\n"
        await message.reply_text(msg)


@app.on_message(filters.command("whitelist") & filters.group)
@capture_err
async def del_filter(_, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/whitelist [WORD|SENTENCE]")
        
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    word = message.text.split(None, 1)[1].strip()
    if not word:
        return await message.reply_text("Usage:\n/whitelist [WORD|SENTENCE]")
        
    await db.remove_chat_filter(chat_id, word)
    await message.reply_text(f"**Whitelisted {word}.**")


@app.on_message(filters.text & filters.group, group=8)
async def blacklist_filters_re(client, message):
    text = message.text.lower().strip()
    if not text:
        return
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return
        
    # Skip admins/sudo
    try:
        member = await app.get_chat_member(chat_id, user.id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
             return
    except:
        pass
        
    sudoers = await db.get_sudoers()
    if user.id in sudoers or user.id == config.OWNER_ID:
        return

    list_of_filters = await db.get_chat_filters(chat_id)
    for word in list_of_filters:
        pattern = r"( |^|[^\w])" + re.escape(word) + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            try:
                await message.delete()
                await message.chat.restrict_member(
                    user.id,
                    ChatPermissions(can_send_messages=False),
                    until_date=datetime.now() + timedelta(hours=1),
                )
                await app.send_message(
                    chat_id,
                    f"Muted {user.mention} [`{user.id}`] for 1 hour "
                    + f"due to a blacklist match on {word}.",
                )
            except Exception as e:
                # Silently fail if no permissions or other error
                pass
            return 
