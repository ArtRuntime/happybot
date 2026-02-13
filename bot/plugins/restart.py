# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
import sys
import shutil
import asyncio

from pyrogram import filters, types

from bot import app, db, lang, stop


@app.on_message(filters.command(["restart"]) & app.sudoers)
@lang.language()
async def _restart(_, m: types.Message):
    sent = await m.reply_text(m.lang["restarting"])

    for directory in ["cache", "downloads"]:
        shutil.rmtree(directory, ignore_errors=True)

    await sent.edit_text(m.lang["restarted"])
    asyncio.create_task(stop())
    await asyncio.sleep(2)

    try: os.remove("log.txt")
    except: pass

    os.execl(sys.executable, sys.executable, "-m", "bot")
