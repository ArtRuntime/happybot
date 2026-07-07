from pyrogram import filters, Client
from pyrogram.types import Message, ChatJoinRequest
from pyrogram.enums import ChatMemberStatus

from bot import app, db
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Auto Approve"
__HELP__ = """
**Auto Approve Commands:**

/autoapprove [on|off] - Toggle auto-approval of join requests in this chat.
"""

@app.on_message(filters.command("autoapprove") & filters.group)
@capture_err
async def auto_approve_command(client, message):
    if not message.from_user:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await client.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    if len(message.command) > 1:
        arg = message.command[1].lower()
        if arg in ["on", "yes", "true"]:
            await db.set_auto_approve(chat_id, True)
            await message.reply_text("Auto-approve has been **ENABLED** for this chat.")
        elif arg in ["off", "no", "false"]:
            await db.set_auto_approve(chat_id, False)
            await message.reply_text("Auto-approve has been **DISABLED** for this chat.")
        else:
            await message.reply_text("Usage: /autoapprove [on|off]")
    else:
        status = await db.get_auto_approve(chat_id)
        status_text = "ENABLED" if status else "DISABLED"
        await message.reply_text(f"Auto-approve is currently **{status_text}** for this chat.\nUsage: /autoapprove [on|off]")


@app.on_chat_join_request()
async def auto_approve_handler(client: Client, request: ChatJoinRequest):
    chat = request.chat
    if await db.get_auto_approve(chat.id):
        try:
            await client.approve_chat_join_request(chat.id, request.from_user.id)
            # Optional: Send a welcome message or log? keeping it silent for now as per simple port requirements
        except Exception as e:
            pass
