import httpx
from io import BytesIO
from pyrogram import filters, Client
from pyrogram.types import Message
from bot import app
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Quotly"
__HELP__ = """
**Quotly:**
Create a sticker quote from messages.

/q - Quote the replied message.
/q <count> - Quote the last <count> messages (replying to the first one).
/q r - Quote with reply context.
"""

async def get_user_details(message: Message):
    user_id = 1
    name = "Unknown"
    username = None
    photo = None
    
    if message.from_user:
        user_id = message.from_user.id
        name = message.from_user.first_name + (f" {message.from_user.last_name}" if message.from_user.last_name else "")
        username = message.from_user.username
        if message.from_user.photo:
            photo = {
                "small_file_id": message.from_user.photo.small_file_id,
                "small_photo_unique_id": message.from_user.photo.small_photo_unique_id,
                "big_file_id": message.from_user.photo.big_file_id,
                "big_photo_unique_id": message.from_user.photo.big_photo_unique_id,
            }
            
    elif message.sender_chat:
        user_id = message.sender_chat.id
        name = message.sender_chat.title
        username = message.sender_chat.username
        if message.sender_chat.photo:
             photo = {
                "small_file_id": message.sender_chat.photo.small_file_id,
                # Mapping might differ for chat photo, but usually similar structure
                "small_photo_unique_id": message.sender_chat.photo.small_photo_unique_id,
                "big_file_id": message.sender_chat.photo.big_file_id,
                "big_photo_unique_id": message.sender_chat.photo.big_photo_unique_id,
            }
            
    return user_id, name, username, photo

async def message_to_dict(message: Message, is_reply=False):
    uid, name, username, photo = await get_user_details(message)
    
    msg_dict = {
        "chatId": uid,
        "text": message.text or message.caption or "",
        "avatar": True,
        "from": {
            "id": uid,
            "name": name,
            "username": username,
            "photo": photo,
            "type": message.chat.type.name.lower()
        },
        "entities": [],
        "replyMessage": {}
    }
    
    # Entities
    entities = message.entities or message.caption_entities
    if entities:
        msg_dict["entities"] = [
            {
                "type": e.type.name.lower(),
                "offset": e.offset,
                "length": e.length
            } for e in entities
        ]

    # Reply context
    if is_reply and message.reply_to_message:
        r_uid, r_name, _, _ = await get_user_details(message.reply_to_message)
        msg_dict["replyMessage"] = {
            "name": r_name,
            "text": message.reply_to_message.text or message.reply_to_message.caption or "",
            "chatId": r_uid
        }
        
    return msg_dict

async def create_quotly(messages, is_reply=False):
    payload = {
        "type": "quote",
        "format": "png",
        "backgroundColor": "#1b1429",
        "messages": []
    }
    
    for msg in messages:
        payload["messages"].append(await message_to_dict(msg, is_reply))
        
    async with httpx.AsyncClient() as http:
        resp = await http.post("https://bot.lyo.su/quote/generate.png", json=payload, timeout=20.0)
        if resp.status_code != 200:
            return None
        return resp.content

@app.on_message(filters.command(["q", "quotly"]) & filters.group)
@capture_err
async def quotly_cmd(client, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a message.")
        
    is_reply = False
    count = 1
    
    if len(message.command) > 1:
        arg = message.command[1]
        if arg.isdigit():
            count = int(arg)
            if count < 1: count = 1
            if count > 20: count = 20
        elif arg == "r":
            is_reply = True

    msg = await message.reply_text("Creating quote...")
    
    try:
        messages = []
        if count > 1:
            # Get range of messages starting from reply
            # Pyrogram get_messages with range?
            # get_messages(chat_id, message_ids=[start ... start+count])
            # ids must be consecutive? Not always.
            # Usually we use get_history but that's for previous.
            # If we want messages AFTER the reply, we need ids + 1, + 2 etc. assuming they exist.
            # But message IDs might be skipped.
            # Best way is to use get_history(offset_id=...) but that's going back.
            # Here we likely want the replied message AND SUBSEQUENT messages?
            # Or replied message and PREVIOUS?
            # MissKaty implementation: range(reply.id, reply.id + count)
            # This assumes consecutive IDs.
            
            ids = list(range(message.reply_to_message.id, message.reply_to_message.id + count))
            msgs = await client.get_messages(message.chat.id, list(ids))
            # Filter empty/service messages if needed
            for m in msgs:
                if m and not m.empty:
                    messages.append(m)
        else:
            messages.append(message.reply_to_message)
            
        sticker_bytes = await create_quotly(messages, is_reply)
        
        if sticker_bytes:
            bio = BytesIO(sticker_bytes)
            bio.name = "quote.webp"
            await message.reply_sticker(bio)
            await msg.delete()
        else:
            await msg.edit("Failed to create quote (API Error).")
            
    except Exception as e:
        await msg.edit(f"Error: {e}")
