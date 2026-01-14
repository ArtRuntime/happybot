# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types

from bot import app, db, lang, queue
from bot.helpers import can_manage_vc


@app.on_message(filters.command(["loop"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _loop(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])

    current = await queue.get_current(m.chat.id)
    if not current:
        return await m.reply_text(m.lang["not_playing"])

    loop_count = 1
    if len(m.command) > 1:
        try:
            loop_count = int(m.command[1])
        except ValueError:
            return await m.reply_text("Usage: /loop [count] (e.g. /loop 10)")
    
    if loop_count < 1:
        return await m.reply_text("Loop count must be at least 1.")
        
    if loop_count > 50:
        return await m.reply_text("Max loop count is 50 to prevent spam.")

    # Loop logic: Insert copies of current track to front of queue
    # Using insert_front means they will play NEXT.
    # To maintain order (if we care), we should insert them such that
    # the first one plays next, the second one plays after that, etc.
    # Since lpush adds to HEAD:
    # Queue: [A, B]
    # LPUSH(X) -> [X, A, B]
    # LPUSH(X) -> [X, X, A, B]
    # So iterating and calling insert_front does exactly what we want.
    
    await m.reply_text(f"🔄 **Looping:** Adding `{current.title}` {loop_count} times to queue...")
    
    for _ in range(loop_count):
        # We must create a new object or deepcopy if we were using objects,
        # but since we serialize to JSON immediately in queue.insert_front,
        # passing the same object is safe.
        await queue.insert_front(m.chat.id, current)
    
    await m.reply_text(f"✅ Looped **{loop_count}** times.")
