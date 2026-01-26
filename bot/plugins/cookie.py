from pyrogram import filters, types
from bot import app, config, logger
from pathlib import Path
import os

@app.on_message(filters.command("addfallback") & app.sudoers)
async def add_fallback(client, message: types.Message):
    doc = None
    
    # 1. Check if file is attached to the command message
    if message.document:
        doc = message.document
    # 2. Check if user replied to a message with a document
    elif message.reply_to_message and message.reply_to_message.document:
        doc = message.reply_to_message.document
        
    if not doc:
        return await message.reply_text("❌ Please reply to a cookie file (.txt/.json) or upload it with the caption `/addfallback`.")
    
    if not doc.file_name or not doc.file_name.lower().endswith((".txt", ".json")):
        return await message.reply_text("❌ File must be a .txt or .json (Netscape/JSON cookie) file.")

    try:
        # Ensure directory exists
        folder = "bot/cookies"
        if not os.path.exists(folder):
            os.makedirs(folder)
            
        path = f"{folder}/cookie_fallback.txt"
        
        if os.path.exists(path):
            os.remove(path)
            action = "Updated"
        else:
            action = "Saved"
            
        # Download file
        target_msg = message.reply_to_message if message.reply_to_message and message.reply_to_message.document else message
        await target_msg.download(file_name=path)
        
        await message.reply_text(f"✅ Fallback cookie {action.lower()} successfully!\n\nThis will be used automatically if primary cookies fail with 'Sign in' error.")
        logger.info(f"Fallback cookie {action.lower()} by {message.from_user.mention}")
    except Exception as e:
        logger.error(f"Failed to save fallback cookie: {e}")
        await message.reply_text(f"❌ Failed to save file: {e}")
