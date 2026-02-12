import re
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.enums import ChatMemberStatus

from bot import app, config, db
from bot.helpers.feds_utils import (
    capture_err, 
    extract_text_and_keyb, 
    extract_urls,
    ikb
)

__MODULE__ = "Filters"
__HELP__ = """
<b>Filter Commands:</b>

/filters - List all filters in the chat.
/filter <name> - Save a filter (reply to a message).
/stop <name> - Delete a filter.
/stopall - Delete all filters.

<b>Supported types:</b> Text, Animation, Photo, Document, Video, Audio, Voice, Sticker.
<b>Note:</b> You can use markdown and buttons in filters.
Expected button format: <code>Text</code>~<code>[Button Name, Link/Callback]</code>
"""

@app.on_message(filters.command(["addfilter", "filter"]) & filters.group)
@capture_err
async def save_filters_handler(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    if len(message.command) < 2 or not message.reply_to_message:
        return await message.reply_text(
            "<b>Usage:</b>\nReply to a message with /filter [FILTER_NAME] To set a new filter."
        )
        
    text = message.text.markdown
    try:
        name = text.split(None, 1)[1].strip()
    except IndexError:
        return await message.reply_text("<b>Usage:</b>\n__/filter [FILTER_NAME]__")
        
    if not name:
        return await message.reply_text("<b>Usage:</b>\n__/filter [FILTER_NAME]__")

    replied_message = message.reply_to_message
    
    # Check if name contains data (e.g. /filter name content)
    # MissKaty logic splits by space, but usually /filter name is used with reply
    # If user provided content in command, use it? MissKaty logic allows it.
    
    # Simplified logic: Rely on replied message primarily
    data = None
    _type = "text"
    file_id = None
    
    if replied_message.text:
        _type = "text"
        data = replied_message.text.markdown
    elif replied_message.caption:
        _type = "media" # Generic media type, we'll refine
        data = replied_message.caption.markdown
    else:
        _type = "media"
        data = ""
        
    if replied_message.sticker:
        _type = "sticker"
        file_id = replied_message.sticker.file_id
    elif replied_message.animation:
        _type = "animation"
        file_id = replied_message.animation.file_id
    elif replied_message.photo:
        _type = "photo"
        file_id = replied_message.photo.file_id
    elif replied_message.document:
        _type = "document"
        file_id = replied_message.document.file_id
    elif replied_message.video:
        _type = "video"
        file_id = replied_message.video.file_id
    elif replied_message.audio:
        _type = "audio"
        file_id = replied_message.audio.file_id
    elif replied_message.voice:
        _type = "voice"
        file_id = replied_message.voice.file_id
    elif replied_message.video_note:
        _type = "video_note"
        file_id = replied_message.video_note.file_id
        
    # Extract buttons from replied message if any
    if replied_message.reply_markup and not re.findall(r"\[.+\,.+\]", data or ""):
        if urls := extract_urls(replied_message.reply_markup):
            response = "\n".join(
                [f"[{text}, {url}]" for name, text, url in urls]
            )
            data = (data or "") + "\n~" + response
            
    name = name.replace("_", " ")
    _filter = {
        "type": _type,
        "data": data,
        "file_id": file_id,
    }
    
    await db.save_filter(chat_id, name, _filter)
    await message.reply_text(f"<u><b>Saved filter {name}.</b></u>")


@app.on_message(filters.command("filters") & filters.group)
@capture_err
async def get_filterss(client, message):
    _filters = await db.get_filters_names(message.chat.id)
    if not _filters:
        return await message.reply_text("<b>No filters in this chat.</b>")
    _filters.sort()
    msg = f"List of filters in {message.chat.title}:\n"
    for _filter in _filters:
        msg += f"<b>-</b> <code>{_filter}</code>\n"
    await message.reply_text(msg)


@app.on_message(filters.command(["stop", "stopfilter"]) & filters.group)
@capture_err
async def del_filter(client, message):
    if len(message.command) < 2:
        return await message.reply_text("<b>Usage:</b>\n__/stop [FILTER_NAME]__")
        
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    name = message.text.split(None, 1)[1].strip()
    if not name:
        return await message.reply_text("<b>Usage:</b>\n__/stop [FILTER_NAME]__")
        
    deleted = await db.delete_filter(chat_id, name)
    if deleted:
        await message.reply_text(f"<b>Deleted filter {name}.</b>")
    else:
        await message.reply_text("<b>No such filter.</b>")


@app.on_message(filters.command("stopall") & filters.group)
@capture_err
async def stop_all(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    member = await app.get_chat_member(chat_id, user_id)
    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply_text("You must be an admin to use this command.")

    _filters = await db.get_filters_names(chat_id)
    if not _filters:
        await message.reply_text("<b>No filters in this chat.</b>")
    else:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("YES, DO IT", callback_data="stop_yes"),
                    InlineKeyboardButton("Cancel", callback_data="stop_no"),
                ]
            ]
        )
        await message.reply_text(
            "<b>Are you sure you want to delete all the filters in this chat forever?</b>",
            reply_markup=keyboard,
        )


@app.on_callback_query(filters.regex("stop_(.*)"))
async def stop_all_cb(client, cb):
    chat_id = cb.message.chat.id
    user_id = cb.from_user.id
    
    try:
        member = await app.get_chat_member(chat_id, user_id)
        if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return await cb.answer("You must be an admin to use this button.", show_alert=True)
    except:
        return

    input_data = cb.data.split("_", 1)[1]
    if input_data == "yes":
        if await db.deleteall_filters(chat_id):
            await cb.message.edit("<b>Successfully deleted all filters on this chat.</b>")
    if input_data == "no":
        await cb.message.delete()


@app.on_message(filters.text & filters.group, group=103)
async def filters_re(client, message):
    text = message.text.lower().strip()
    if not text:
        return
        
    chat_id = message.chat.id
    
    # Need to fetch all filters to check regex or exact match
    # MissKaty checks keys against text with regex search
    list_of_filters = await db.get_filters_names(chat_id)
    if not list_of_filters:
        return

    for word in list_of_filters:
        # Simple word boundary check
        pattern = r"( |^|[^\w])" + re.escape(word) + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            _filter = await db.get_filter(chat_id, word)
            data_type = _filter["type"]
            data = _filter.get("data")
            file_id = _filter.get("file_id")
            
            keyb = None
            if data:
                # Variables replacement
                if "{chat}" in data:
                    data = data.replace("{chat}", message.chat.title)
                if "{name}" in data:
                    user_mention = message.from_user.mention if message.from_user else message.sender_chat.title
                    data = data.replace("{name}", user_mention)
                    
                # Keyboard extraction
                # Using our helper
                data, keyb = extract_text_and_keyb(ikb, data)

            if data_type == "text":
                await message.reply_text(
                    text=data,
                    reply_markup=keyb,
                    disable_web_page_preview=True,
                )
            elif data_type == "sticker":
                await message.reply_sticker(sticker=file_id)
            elif data_type == "animation":
                await message.reply_animation(animation=file_id, caption=data, reply_markup=keyb)
            elif data_type == "photo":
                await message.reply_photo(photo=file_id, caption=data, reply_markup=keyb)
            elif data_type == "document":
                await message.reply_document(document=file_id, caption=data, reply_markup=keyb)
            elif data_type == "video":
                await message.reply_video(video=file_id, caption=data, reply_markup=keyb)
            elif data_type == "audio":
                await message.reply_audio(audio=file_id, caption=data, reply_markup=keyb)
            elif data_type == "voice":
                await message.reply_voice(voice=file_id, caption=data, reply_markup=keyb)
                
            return # Stop after first match
