# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
import shutil
from pyrogram import filters, types

from bot import app, db, lang


@app.on_message(filters.command(["clean", "cleanup"]) & filters.group & ~app.bl_users)
@lang.language()
async def _clean(_, m: types.Message):
    """Clean downloads and cache directories. Sudo only."""
    if m.from_user.id not in app.sudoers:
        return
    
    sent = await m.reply_text("🧹 Cleaning cache, downloads, and database...")
    
    cleaned_files = 0
    cleaned_size = 0
    
    # Clean Mongo DB cache collections
    try:
        await db.cache_metadata.delete_many({})
        await db.stream_cache.delete_many({})
    except Exception as e:
        pass
    
    dirs_to_clean = ["downloads", "cache"]
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            for file in os.listdir(dir_name):
                file_path = os.path.join(dir_name, file)
                try:
                    if os.path.isfile(file_path):
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        cleaned_files += 1
                        cleaned_size += file_size
                except Exception:
                    pass
    
    # Convert size to readable format
    if cleaned_size >= 1024 * 1024:
        size_str = f"{cleaned_size / (1024 * 1024):.2f} MB"
    elif cleaned_size >= 1024:
        size_str = f"{cleaned_size / 1024:.2f} KB"
    else:
        size_str = f"{cleaned_size} bytes"
    
    await sent.edit_text(
        f"✅ <b>Cleanup complete!</b>\n\n"
        f"📁 Files removed: <code>{cleaned_files}</code>\n"
        f"💾 Space freed: <code>{size_str}</code>"
    )
