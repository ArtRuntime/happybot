import asyncio
from pyrogram import filters
from pyrogram.errors import ChatAdminRequired, ChatNotModified, FloodWait
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatPermissions

from bot import app, config, db
from bot.helpers.feds_utils import capture_err, get_urls_from_text

__MODULE__ = "Locks"
__HELP__ = """
<b>Locks Commands:</b>

/lock &lt;type&gt; - Lock a specific message type.
/unlock &lt;type&gt; - Unlock a specific message type.
/locks - View current locks.

<b>Types:</b>
messages, media, other, photo, video, docs, voice, audio, videonote, polls, url, group_info, useradd, pin, all
"""

data = {
    "messages": "can_send_messages",
    "media": "can_send_media_messages",
    "other": "can_send_other_messages",
    "photo": "can_send_photos",
    "video": "can_send_videos",
    "docs": "can_send_documents",
    "voice": "can_send_voice_notes",
    "audio": "can_send_audios",
    "videonote": "can_send_video_notes",
    "url": "can_add_web_page_previews",
    "polls": "can_send_polls",
    "group_info": "can_change_info",
    "useradd": "can_invite_users",
    "pin": "can_pin_messages",
}

async def current_chat_permissions(chat_id):
    perms = []
    try:
        chat = await app.get_chat(chat_id)
        perm = chat.permissions
    except FloodWait as e:
        await asyncio.sleep(e.value)
        chat = await app.get_chat(chat_id)
        perm = chat.permissions
    except Exception:
        return []

    if perm.can_send_messages:
        perms.append("can_send_messages")
    if perm.can_send_media_messages:
        perms.append("can_send_media_messages")
    if perm.can_send_other_messages:
        perms.append("can_send_other_messages")
    if perm.can_send_audios:
        perms.append("can_send_audios")
    if perm.can_send_documents:
        perms.append("can_send_documents")
    if perm.can_send_photos:
        perms.append("can_send_photos")
    if perm.can_send_videos:
        perms.append("can_send_videos")
    if perm.can_send_voice_notes:
        perms.append("can_send_voice_notes")
    if perm.can_send_video_notes:
        perms.append("can_send_video_notes")
    if perm.can_add_web_page_previews:
        perms.append("can_add_web_page_previews")
    if perm.can_send_polls:
        perms.append("can_send_polls")
    if perm.can_change_info:
        perms.append("can_change_info")
    if perm.can_invite_users:
        perms.append("can_invite_users")
    if perm.can_pin_messages:
        perms.append("can_pin_messages")

    return perms


async def tg_lock(message, permissions: list, perm: str, lock: bool):
    if lock:
        if perm not in permissions:
            return await message.reply_text("Already locked.")
        permissions.remove(perm)
    elif perm in permissions:
        return await message.reply_text("Already Unlocked.")
    else:
        permissions.append(perm)

    # Reconstruct ChatPermissions
    # ChatPermissions expects arguments like can_send_messages=True/False
    # Our list `permissions` contains enabled permissions.
    # So if "can_send_messages" is in `permissions`, it's True.
    
    perm_dict = {p: True for p in permissions}
    
    # We must explicitly set False for permissions NOT in the list, 
    # but set_chat_permissions only updates what is passed? 
    # No, it usually replaces permissions object or updates provided fields.
    # If we pass ChatPermissions(**perm_dict), only True values are passed.
    # We need to consider how set_chat_permissions works.
    # Actually, if we only pass what we want to be True, others might default to False or None.
    # To be safe, we should probably construct a full object or trust Pyrogram.
    # MissKatyPyro logic: permissions = {perm: True for perm in list(set(permissions))}
    # This implies only explicitly True permissions are sent.
    
    try:
        await app.set_chat_permissions(message.chat.id, ChatPermissions(**perm_dict))
    except ChatNotModified:
        return await message.reply_text(
            "To unlock this, you have to unlock 'messages' first."
        )
    except Exception as e:
        return await message.reply_text(f"Error: {e}")

    await message.reply_text(("Locked." if lock else "Unlocked."))


@app.on_message(filters.command(["lock", "unlock"]) & filters.group)
@capture_err
async def locks_func(_, message):
    if not message.from_user:
        return
        
    if len(message.command) != 2:
        return await message.reply_text("Usage: /lock <type> or /unlock <type>")

    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Admin check
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    # Check if bot is admin
    try:
        me = await app.get_chat_member(chat_id, app.me.id)
        if not me.privileges or not me.privileges.can_restrict_members:
             return await message.reply_text("I need 'Restrict Members' permission to manage locks.")
    except:
        return await message.reply_text("I am not an admin here!")

    parameter = message.text.strip().split(None, 1)[1].lower()
    state = message.command[0].lower()

    if parameter not in data and parameter != "all":
        return await message.reply_text("Invalid parameter. See /help or /locks help.")

    permissions = await current_chat_permissions(chat_id)

    if parameter in data:
        await tg_lock(message, permissions, data[parameter], state == "lock")
    elif parameter == "all" and state == "lock":
        try:
            await app.set_chat_permissions(chat_id, ChatPermissions(all_perms=False))
            await message.reply_text(f"Locked Everything in {message.chat.title}")
        except Exception as e:
            await message.reply_text(f"Error: {e}")

    elif parameter == "all" and state == "unlock":
        try:
            await app.set_chat_permissions(
                chat_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                    can_change_info=True,
                    can_invite_users=True,
                    can_pin_messages=True,
                ),
            )
            await message.reply(f"Unlocked Everything in {message.chat.title}")
        except Exception as e:
            await message.reply_text(f"Error: {e}")


@app.on_message(filters.command("locks") & filters.group)
@capture_err
async def locktypes(_, message):
    permissions = await current_chat_permissions(message.chat.id)

    if not permissions:
        return await message.reply_text("No Permissions Found (Everything Locked?).")

    perms = "".join(f"<u>{i}</u>\n" for i in permissions)
    await message.reply_text(f"<b>Unlocked Permissions:</b>\n\n{perms}")


@app.on_message(filters.text & filters.group, group=69)
async def url_detector(_, message):
    if message.sender_chat or not message.from_user:
        return
    user = message.from_user
    chat_id = message.chat.id
    text = message.text.lower().strip()

    if not text:
        return
        
    # Check if user is admin
    try:
        member = await app.get_chat_member(chat_id, user.id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return
    except:
        pass
    
    sudoers = await db.get_sudoers()
    if user.id in sudoers or user.id == config.OWNER_ID:
        return

    if get_urls_from_text(text):
        permissions = await current_chat_permissions(chat_id)
        if "can_add_web_page_previews" not in permissions:
            try:
                await message.delete()
            except Exception:
                pass
