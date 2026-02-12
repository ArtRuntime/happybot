from pyrogram import filters, enums
from pyrogram.types import Message
from bot import app, db
from bot.helpers.feds_utils import capture_err

__MODULE__ = "SangMata"
__HELP__ = """
<b>SangMata:</b>
Monitor user name/username changes in the chat.

/sangmata [on/off] - Enable/disable SangMata in the group.
"""

@app.on_message(filters.command(["sangmata", "sangmata_set"]) & filters.group)
@capture_err
async def sangmata_set(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /sangmata [on/off]")
        
    member = await client.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
         return await message.reply_text("You need to be an admin to use this command.")

    arg = message.command[1].lower()
    if arg == "on":
        await db.set_sangmata_status(message.chat.id, True)
        await message.reply_text("SangMata enabled in this chat.")
    elif arg == "off":
        await db.set_sangmata_status(message.chat.id, False)
        await message.reply_text("SangMata disabled in this chat.")
    else:
        await message.reply_text("Usage: /sangmata [on/off]")

@app.on_message(filters.group & ~filters.bot, group=69)
async def sangmata_check(client, message):
    if message.sender_chat:
        return
        
    user = message.from_user
    if not user:
        return
        
    # Check if enabled in chat
    if not await db.is_sangmata_on(message.chat.id):
        return

    # Check previous data
    prev_username, prev_first, prev_last = await db.get_sangmata_user(user.id)
    
    # If new user, save and return
    if prev_first is None:
        await db.update_sangmata_user(user.id, user.username, user.first_name, user.last_name)
        return

    # Compare
    changes = []
    
    current_username = user.username
    current_first = user.first_name
    current_last = user.last_name
    
    if prev_username != current_username:
        u_prev = f"@{prev_username}" if prev_username else "No Username"
        u_curr = f"@{current_username}" if current_username else "No Username"
        changes.append(f"• Username changed from {u_prev} to {u_curr}")
        
    if prev_first != current_first:
        changes.append(f"• First Name changed from {prev_first} to {current_first}")
        
    if prev_last != current_last:
        l_prev = prev_last if prev_last else "No Last Name"
        l_curr = current_last if current_last else "No Last Name"
        changes.append(f"• Last Name changed from {l_prev} to {l_curr}")
        
    if changes:
        text = f"👀 <b>SangMata Watcher</b>\n\nUser: {user.mention} [<code>{user.id}</code>]\n"
        text += "\n".join(changes)
        await message.reply_text(text)
        
        # Update DB
        await db.update_sangmata_user(user.id, current_username, current_first, current_last)
