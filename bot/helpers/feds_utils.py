import traceback
from functools import wraps
from string import ascii_lowercase
from re import findall
from bot import app, logger, config

def get_urls_from_text(text: str) -> list:
    regex = r"""(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]
                [.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(
                \([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\
                ()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’]))""".strip()
    return [x[0] for x in findall(regex, text)]

from pyrogram import enums
from pyrogram.types import Message, CallbackQuery

def capture_err(func):
    @wraps(func)
    async def capture(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except Exception as err:
            exc = traceback.format_exc()
            logger.error(f"Error in {func.__name__}: {exc}")
            if isinstance(message, Message):
                await message.reply_text(f"An error occurred: {err}")
            elif isinstance(message, CallbackQuery):
                await message.answer(f"An error occurred: {err}", show_alert=True)
            # If logger group is set, send error there
            if config.LOGGER_ID:
                 try:
                     await client.send_message(
                         config.LOGGER_ID,
                         f"⚠️ **Error in {func.__name__}**\n\n`{exc}`"
                     )
                 except:
                     pass
    return capture

async def alpha_to_int(user_id_alphabet: str) -> int:
    alphabet = list(ascii_lowercase)[:10]
    user_id = ""
    for i in user_id_alphabet:
        index = alphabet.index(i)
        user_id += str(index)
    return int(user_id)


async def int_to_alpha(user_id: int) -> str:
    alphabet = list(ascii_lowercase)[:10]
    user_id = str(user_id)
    return "".join(alphabet[int(i)] for i in user_id)


async def extract_userid(message, text: str):
    def is_int(text: str):
        try:
            int(text)
        except ValueError:
            return False
        return True

    text = text.strip()

    if is_int(text):
        return int(text)

    entities = message.entities
    if not entities or len(entities) < 2:
        return (await app.get_users(text)).id
    entity = entities[1]
    if entity.type == enums.MessageEntityType.MENTION:
        return (await app.get_users(text)).id
    if entity.type == enums.MessageEntityType.TEXT_MENTION:
        return entity.user.id
    return None


async def extract_user_and_reason(message, sender_chat=False):
    args = message.text.strip().split()
    text = message.text
    user = None
    reason = None
    if message.reply_to_message:
        reply = message.reply_to_message
        # if reply to a message and no reason is given
        if reply.from_user:
            id_ = reply.from_user.id

        elif reply.sender_chat and reply.sender_chat != message.chat.id and sender_chat:
            id_ = reply.sender_chat.id
        else:
            return None, None
        reason = None if len(args) < 2 else text.split(None, 1)[1]
        return id_, reason

    # if not reply to a message and no reason is given
    if len(args) == 2:
        user = text.split(None, 1)[1]
        return await extract_userid(message, user), None

    # if reason is given
    if len(args) > 2:
        user, reason = text.split(None, 2)[1:]
        return await extract_userid(message, user), reason

    return user, reason


    return user, reason


async def extract_user(message):
    return (await extract_user_and_reason(message))[0]

# Keyboard Helpers
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def keyboard(buttons_list, row_width: int = 2):
    """
    Buttons builder, pass buttons in a list and it will
    return pyrogram.types.InlineKeyboardMarkup object
    Ex: keyboard([["click here", "https://google.com"]])
    if theres, a url, it will make url button, else callback button
    """
    buttons = []
    for i in buttons_list:
        text = str(i[0])
        data = str(i[1])
        if get_urls_from_text(data):
            buttons.append(InlineKeyboardButton(text=text, url=data))
        else:
            buttons.append(InlineKeyboardButton(text=text, callback_data=data))
            
    # Chunk into rows
    lines = [buttons[i:i + row_width] for i in range(0, len(buttons), row_width)]
    return InlineKeyboardMarkup(lines)

def ikb(data: dict, row_width: int = 2):
    """
    Converts a dict to pyrogram buttons
    Ex: ikb({"click here": "this is callback data"})
    """
    return keyboard(data.items(), row_width=row_width)

def extract_text_and_keyb(ikb, text: str, row_width: int = 2):
    keyboard_markup = None
    try:
        text = text.strip()
        text = text.removeprefix("`")
        text = text.removesuffix("`")
        
        if "~" in text:
            text, keyb_str = text.split("~", 1)
            
            keyboard_data = {}
            # Regex to find [Button Name, link/callback]
            # MissKatyPyro regex: r"\[.+\,.+\]"
            keyb_matches = findall(r"\[.+,.+\]", keyb_str)
            
            for btn_str in keyb_matches:
                # Remove brackets
                btn_str = btn_str[1:-1]
                # Split by comma
                if "," in btn_str:
                    btn_parts = btn_str.split(",", 1)
                    btn_txt = btn_parts[0].strip()
                    btn_url = btn_parts[1].strip()
                    
                    # Store in dict
                    keyboard_data[btn_txt] = btn_url
            
            if keyboard_data:
                keyboard_markup = ikb(keyboard_data, row_width)
        
    except Exception:
        return text, None
        
    return text, keyboard_markup

def extract_urls(reply_markup):
    urls = []
    if reply_markup.inline_keyboard:
        buttons = reply_markup.inline_keyboard
        for i, row in enumerate(buttons):
            for j, button in enumerate(row):
                if button.url:
                    name = (
                        "\n~\nbutton"
                        if i * len(row) + j == 0
                        else f"button{i * len(row) + j + 1}"
                    )
                    urls.append((f"{name}", button.text, button.url))
    return urls

import asyncio
import os

async def take_ss(video_file: str, output_file: str = None) -> str:
    if output_file is None:
        output_file = video_file + ".jpg"
        
    cmd = [
        "ffmpeg", "-ss", "00:00:01", "-i", video_file,
        "-vframes", "1", "-q:v", "2", "-y", output_file
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.communicate()
    
    if os.path.exists(output_file):
        return output_file
    return None

def split_arr(arr, size):
    return [arr[i : i + size] for i in range(0, len(arr), size)]
