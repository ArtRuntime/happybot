from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserAdminInvalid, ChatAdminRequired
from bot import app
from bot.helpers.feds_utils import capture_err, extract_user_and_reason

__MODULE__ = "Admin"
__HELP__ = """
<b>Admin Commands:</b>

/ban [user] [reason] - Ban a user from the chat
/unban [user] - Unban a user from the chat

Reply to a user's message or provide username/ID.
"""

@app.on_message(filters.command("ban") & filters.group)
@capture_err
async def ban_user(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if command user is admin
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")
    
    # Check if bot has ban permissions
    try:
        bot_member = await app.get_chat_member(chat_id, app.me.id)
        if not bot_member.privileges or not bot_member.privileges.can_restrict_members:
            return await message.reply_text("I need 'Ban Users' permission to do this.")
    except:
        return await message.reply_text("I am not an admin here!")
    
    # Extract user and reason
    user_to_ban, reason = await extract_user_and_reason(message)
    
    if not user_to_ban:
        return await message.reply_text(
            "Reply to a user's message or provide username/ID.\n"
            "Usage: /ban [user] [reason]"
        )
    
    # Check if target is admin
    try:
        target_member = await app.get_chat_member(chat_id, user_to_ban)
        if target_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return await message.reply_text("I cannot ban an admin!")
    except:
        pass
    
    # Ban the user
    try:
        await app.ban_chat_member(chat_id, user_to_ban)
        
        # Get user info for response
        try:
            user_info = await app.get_users(user_to_ban)
            user_mention = user_info.mention
        except:
            user_mention = f"User {user_to_ban}"
        
        text = f"<b>Banned</b> {user_mention}"
        if reason:
            text += f"\n<b>Reason:</b> {reason}"
        
        await message.reply_text(text)
        
    except UserAdminInvalid:
        await message.reply_text("I cannot ban this user (they might be an admin).")
    except ChatAdminRequired:
        await message.reply_text("I need admin rights to ban users.")
    except Exception as e:
        await message.reply_text(f"Failed to ban user: {e}")


@app.on_message(filters.command("unban") & filters.group)
@capture_err
async def unban_user(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if command user is admin
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")
    
    # Check if bot has ban permissions
    try:
        bot_member = await app.get_chat_member(chat_id, app.me.id)
        if not bot_member.privileges or not bot_member.privileges.can_restrict_members:
            return await message.reply_text("I need 'Ban Users' permission to do this.")
    except:
        return await message.reply_text("I am not an admin here!")
    
    # Extract user
    user_to_unban, _ = await extract_user_and_reason(message)
    
    if not user_to_unban:
        return await message.reply_text(
            "Reply to a user's message or provide username/ID.\n"
            "Usage: /unban [user]"
        )
    
    # Unban the user
    try:
        await app.unban_chat_member(chat_id, user_to_unban)
        
        # Get user info for response
        try:
            user_info = await app.get_users(user_to_unban)
            user_mention = user_info.mention
        except:
            user_mention = f"User {user_to_unban}"
        
        await message.reply_text(f"<b>Unbanned</b> {user_mention}")
        
    except ChatAdminRequired:
        await message.reply_text("I need admin rights to unban users.")
    except Exception as e:
        await message.reply_text(f"Failed to unban user: {e}")
