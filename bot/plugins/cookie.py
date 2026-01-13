from pyrogram import filters, types
from bot import app, config, logger
from pathlib import Path
import os

@app.on_message(filters.command("addfallback") & app.sudoers)
async def add_fallback(client: app, message: types.Message):
    if not message.reply_to_message and not message.document:
        return await message.reply_text("❌ Please reply to a cookie file or send it with the command.")

    doc = message.document or message.reply_to_message.document
    if not doc:
        return await message.reply_text("❌ No document found.")
    
    if not doc.file_name.endswith((".txt", ".json")):
        return await message.reply_text("❌ File must be a .txt or .json (Netscape/JSON cookie) file.")

    try:
        path = "bot/cookies/cookie_fallback.txt"
        if os.path.exists(path):
            os.remove(path)
            action = "Updated"
        else:
            action = "Saved"
            
        file_path = await message.download(file_name=path)
        await message.reply_text(f"✅ Fallback cookie {action.lower()} successfully!\n\nThis will be used automatically if primary cookies fail with 'Sign in' error.")
        logger.info(f"Fallback cookie {action.lower()} by {message.from_user.mention}")
    except Exception as e:
        logger.error(f"Failed to save fallback cookie: {e}")
        await message.reply_text(f"❌ Failed to save file: {e}")
