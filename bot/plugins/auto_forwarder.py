from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

from bot import app, config, db
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Auto Forwarder"
__HELP__ = """
<b>Auto Forwarder Commands:</b>

/addforward &lt;dest_chat_id&gt; - Add a destination for auto-forwarding from the current chat.
/delforward &lt;dest_chat_id&gt; - Remove a destination.
/forwards - List current forwarding destinations.

<b>Note:</b> The bot must be admin in both source and destination chats.
"""

@app.on_message(filters.command("addforward") & filters.group)
@capture_err
async def add_forward_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    if len(message.command) < 2:
        return await message.reply_text("Usage: /addforward <destination_chat_id>")
        
    try:
        dest_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("Invalid Chat ID.")
        
    # Verify bot can send to dest
    try:
        test = await app.send_message(dest_id, "Testing Auto-Forward connection...")
        await test.delete()
    except Exception as e:
        return await message.reply_text(f"I cannot send messages to that chat. Make sure I am a member/admin there.\nError: {e}")
        
    await db.add_forward(chat_id, dest_id)
    await message.reply_text(f"Successfully added forward to `{dest_id}`.")


@app.on_message(filters.command("delforward") & filters.group)
@capture_err
async def del_forward_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    if len(message.command) < 2:
        return await message.reply_text("Usage: /delforward <destination_chat_id>")
        
    try:
        dest_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("Invalid Chat ID.")
        
    await db.remove_forward(chat_id, dest_id)
    await message.reply_text(f"Removed forward to `{dest_id}`.")


@app.on_message(filters.command("forwards") & filters.group)
@capture_err
async def list_forwards_cmd(client, message):
    chat_id = message.chat.id
    dests = await db.get_forwards(chat_id)
    
    if not dests:
        return await message.reply_text("No forwarding set for this chat.")
        
    text = "Auto-Forward Destinations:\n"
    for dest in dests:
        text += f"- `{dest}`\n"
        
    await message.reply_text(text)


@app.on_message(filters.incoming & filters.group, group=104)
async def auto_forward_handler(client, message):
    dests = await db.get_forwards(message.chat.id)
    if not dests:
        return

    for dest_id in dests:
        try:
            # Re-check types to avoid forwarding service messages if needed
            if message.service:
                continue
                
            await message.forward(dest_id)
        except FloodWait as e:
            # Don't sleep in handler? just skip or log
            pass
        except Exception:
            pass
