# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

import asyncio
from pyrogram import enums, filters, types

from bot import app, config, db, lang
from bot.helpers import buttons, utils


@app.on_message(filters.command(["help"]) & filters.private & ~app.bl_users)
@lang.language()
async def _help(_, m: types.Message):
    import psutil
    import os
    
    # Calculate CPU/RAM usage
    pid = os.getpid()
    process = psutil.Process(pid)
    cpu_percent = process.cpu_percent(interval=0.1)
    memory_info = process.memory_info()
    memory_percent = process.memory_percent()
    
    # Calculate Cache storage details
    limit_bytes, limit_str = await db.get_max_cache_limit()
    
    # Calculate current cache size from database
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$file_size"}}}]
    cursor = await db.cache_metadata.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    total_bytes = result[0]["total"] if result else 0
    
    # Storage left
    left_bytes = max(0, limit_bytes - total_bytes)
    
    # Human-readable formatting helper
    def get_size_str(bytes_val):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"
        
    current_str = get_size_str(total_bytes)
    left_str = get_size_str(left_bytes)
    
    health_text = (
        f"🖥️ <b>Bot Health Status:</b>\n"
        f"├ <b>CPU Usage:</b> <code>{cpu_percent}%</code>\n"
        f"└ <b>RAM Usage:</b> <code>{memory_info.rss / 1024**2:.2f} MB ({memory_percent:.1f}%)</code>\n\n"
        f"💾 <b>Cache Storage:</b>\n"
        f"├ <b>Used:</b> <code>{current_str}</code>\n"
        f"├ <b>Limit:</b> <code>{limit_str}</code>\n"
        f"└ <b>Storage Left:</b> <code>{left_str}</code>\n\n"
    )
    
    help_menu_text = health_text + m.lang["help_menu"]
    
    await m.reply_text(
        text=help_menu_text,
        reply_markup=buttons.help_markup(m.lang),
        quote=True,
    )


@app.on_message(filters.command(["start"]))
@lang.language()
async def start(_, message: types.Message):
    if message.from_user.id in app.bl_users and message.from_user.id not in db.notified:
        return await message.reply_text(message.lang["bl_user_notify"])

    if len(message.command) > 1 and message.command[1] == "help":
        return await _help(_, message)

    private = message.chat.type == enums.ChatType.PRIVATE
    _text = (
        message.lang["start_pm"].format(message.from_user.first_name, app.name)
        if private
        else message.lang["start_gp"].format(app.name)
    )

    key = buttons.start_key(message.lang, private)
    await message.reply_photo(
        photo=config.START_IMG,
        caption=_text,
        reply_markup=key,
        quote=not private,
    )

    if private:
        if await db.is_user(message.from_user.id):
            return
        await utils.send_log(message)
        await db.add_user(message.from_user.id)
    else:
        if await db.is_chat(message.chat.id):
            return
        await utils.send_log(message, True)
        await db.add_chat(message.chat.id)


@app.on_message(filters.new_chat_members, group=7)
@lang.language()
async def _new_member(_, message: types.Message):
    if message.chat.type != enums.ChatType.SUPERGROUP:
        return await message.chat.leave()

    await asyncio.sleep(3)
    for member in message.new_chat_members:
        if member.id == app.id:
            if await db.is_chat(message.chat.id):
                return
            await utils.send_log(message, True)
            await db.add_chat(message.chat.id)


@app.on_message(group=-1)
async def auto_register_chats(_, message: types.Message):
    if not message.chat:
        return
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if not await db.is_chat(message.chat.id):
            await db.add_chat(message.chat.id)
    elif message.chat.type == enums.ChatType.PRIVATE:
        if message.from_user and not await db.is_user(message.from_user.id):
            await db.add_user(message.from_user.id)
