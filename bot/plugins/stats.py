# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
import platform
import sys
import time
from datetime import timedelta

import psutil
from pyrogram import __version__, filters, types
from pytgcalls import __version__ as pytgver

from bot import app, config, db, lang, userbot
from bot.plugins import all_modules


# Store bot start time
BOT_START_TIME = time.time()


def get_readable_time(seconds: int) -> str:
    """Convert seconds to readable time format"""
    return str(timedelta(seconds=int(seconds)))


def get_size(bytes_size: int) -> str:
    """Convert bytes to readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


@app.on_message(filters.command(["stats"]) & filters.group & ~app.bl_users)
@lang.language()
async def _stats(_, m: types.Message):
    sent = await m.reply_photo(
        photo=config.PING_IMG,
        caption=m.lang["stats_fetching"],
    )

    # Basic bot info
    pid = os.getpid()
    process = psutil.Process(pid)
    
    # System info
    cpu_percent = process.cpu_percent(interval=0.5)
    memory_info = process.memory_info()
    memory_percent = process.memory_percent()
    
    # System-wide stats
    total_memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    
    # Network stats
    net_io = psutil.net_io_counters()
    
    # Uptime
    uptime = get_readable_time(time.time() - BOT_START_TIME)
    
    # Database stats
    total_chats = await db.count_chats()
    total_users = await db.count_users()
    
    # Build user stats text
    _utext = f"""
<b>🤖 {app.name} Statistics</b>

<b>📊 Bot Info:</b>
├ <b>Uptime:</b> <code>{uptime}</code>
├ <b>Modules:</b> <code>{len(all_modules)}</code>
├ <b>Assistants:</b> <code>{len(userbot.clients)}</code>
├ <b>Python:</b> <code>{sys.version.split()[0]}</code>
├ <b>Pyrogram:</b> <code>{__version__}</code>
└ <b>PyTgCalls:</b> <code>{pytgver}</code>

<b>👥 Users & Chats:</b>
├ <b>Total Chats:</b> <code>{total_chats}</code>
├ <b>Total Users:</b> <code>{total_users}</code>
├ <b>Blacklisted:</b> <code>{len(db.blacklisted_chats) + len(db.blacklisted_users)}</code>
└ <b>Sudo Users:</b> <code>{len(app.sudoers)}</code>

<b>💻 System Resources:</b>
├ <b>CPU Usage:</b> <code>{cpu_percent}%</code>
├ <b>RAM Usage:</b> <code>{memory_info.rss / 1024**2:.2f} MB ({memory_percent:.1f}%)</code>
├ <b>Total RAM:</b> <code>{total_memory.total / 1024**3:.2f} GB</code>
├ <b>Available RAM:</b> <code>{total_memory.available / 1024**3:.2f} GB</code>
└ <b>CPU Cores:</b> <code>{psutil.cpu_count(logical=False)} Physical, {psutil.cpu_count()} Logical</code>

<b>💾 Storage:</b>
├ <b>Used:</b> <code>{disk.used / 1024**3:.2f} GB</code>
├ <b>Free:</b> <code>{disk.free / 1024**3:.2f} GB</code>
├ <b>Total:</b> <code>{disk.total / 1024**3:.2f} GB</code>
└ <b>Usage:</b> <code>{disk.percent}%</code>

<b>🌐 Network:</b>
├ <b>Sent:</b> <code>{get_size(net_io.bytes_sent)}</code>
└ <b>Received:</b> <code>{get_size(net_io.bytes_recv)}</code>
"""

    # Add sudo-only info
    if m.from_user.id in app.sudoers:
        # Disk I/O
        disk_io = psutil.disk_io_counters()
        
        # System load
        load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
        
        _utext += f"""
<b>🔧 Advanced Stats (Sudo Only):</b>
├ <b>Platform:</b> <code>{platform.system()} {platform.release()}</code>
├ <b>Architecture:</b> <code>{platform.machine()}</code>
├ <b>Processor:</b> <code>{platform.processor() or 'Unknown'}</code>
├ <b>Load Average:</b> <code>{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}</code>
├ <b>Disk Read:</b> <code>{get_size(disk_io.read_bytes)}</code>
├ <b>Disk Write:</b> <code>{get_size(disk_io.write_bytes)}</code>
├ <b>Boot Time:</b> <code>{get_readable_time(time.time() - psutil.boot_time())} ago</code>
└ <b>Process ID:</b> <code>{pid}</code>
"""

    await sent.edit_caption(_utext)
