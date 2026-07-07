import time
import re
from pyrogram import filters, enums
from pyrogram.types import Message
from bot import app, db
from bot.helpers.feds_utils import capture_err

__MODULE__ = "AFK"
__HELP__ = """
<b>AFK (Away From Keyboard):</b>
Tell others you are busy.

/afk [reason] - Set yourself as AFK.
/afk [reply to media] - Set AFK with media.
"""

# Helper to format time
def get_readable_time(seconds: int) -> str:
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for i in range(len(time_list)):
        time_list[i] = str(time_list[i]) + time_suffix_list[i]
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "

    time_list.reverse()
    ping_time += ":".join(time_list)

    return ping_time

@app.on_message(filters.command("afk") & filters.group)
@capture_err
async def afk_cmd(client, message):
    if message.sender_chat or not message.from_user:
         return
         
    user_id = message.from_user.id
    is_afk, _ = await db.is_afk(user_id)
    
    if is_afk:
        await db.remove_afk(user_id)
        await message.reply_text(f"{message.from_user.mention} is no longer AFK.")
        return

    reason = None
    media = None
    afk_type = "text"
    
    # Reason extraction
    if len(message.command) > 1 and not message.reply_to_message:
         reason = message.text.split(None, 1)[1]
    elif message.reply_to_message:
         if len(message.command) > 1:
              reason = message.text.split(None, 1)[1]
              
         if message.reply_to_message.animation:
              afk_type = "animation"
              media = message.reply_to_message.animation.file_id
         elif message.reply_to_message.photo:
              afk_type = "photo"
              media = message.reply_to_message.photo.file_id
         elif message.reply_to_message.sticker:
              if message.reply_to_message.sticker.is_animated:
                   afk_type = "text" # Treat animated sticker as text for now or animation if supported
              else:
                   afk_type = "photo" 
                   media = message.reply_to_message.sticker.file_id # Convert sticker to photo logic needs download
                   # For simplicity, treat sticker reply as just reason unless we download it
                   # I'll enable sticker file_id storage but it might not verify as photo
                   # Let's stick to simple types
                   pass

    details = {
        "type": afk_type,
        "time": time.time(),
        "reason": reason,
        "media": media
    }
    
    await db.add_afk(user_id, details)
    await message.reply_text(f"{message.from_user.mention} is now AFK.")

# AFK Watcher
@app.on_message(filters.group & ~filters.bot, group=99)
async def afk_watcher(client, message):
    if message.sender_chat or not message.from_user:
        return
        
    user_id = message.from_user.id
    
    # Check if sender is AFK (Remove AFK)
    # Ignore if message is /afk
    if message.text and message.text.startswith(("/afk", "!afk")):
         return
         
    is_afk, data = await db.is_afk(user_id)
    if is_afk:
        await db.remove_afk(user_id)
        # Calculate time
        afk_time = int(time.time() - data["time"])
        seen_ago = get_readable_time(afk_time)
        await message.reply_text(f"{message.from_user.mention} is back online!\nWas AFK for: {seen_ago}")
        return

    # Check if replied user is AFK
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if target_id == user_id: return # Reply to self
        
        is_target_afk, data = await db.is_afk(target_id)
        if is_target_afk:
             afk_time = int(time.time() - data["time"])
             seen_ago = get_readable_time(afk_time)
             reason = data.get("reason")
             
             text = f"{message.reply_to_message.from_user.mention} is AFK.\nTime: {seen_ago}"
             if reason:
                  text += f"\nReason: {reason}"
                  
             if data["type"] == "animation" and data["media"]:
                  await message.reply_animation(data["media"], caption=text)
             elif data["type"] == "photo" and data["media"]:
                  await message.reply_photo(data["media"], caption=text)
             else:
                  await message.reply_text(text)
        return

    # Check mentions
    if message.entities:
        for entity in message.entities:
            if entity.type == enums.MessageEntityType.MENTION:
                # Extract username
                username = message.text[entity.offset:entity.offset+entity.length]
                # We need user_id from username. 
                # This requires get_users call which is expensive/rate limited.
                # MissKaty does it.
                # I'll skip username AFK check to avoid heavy API usage unless crucial.
                # Text mentions (with user object) are easier.
                pass
            elif entity.type == enums.MessageEntityType.TEXT_MENTION:
                target_id = entity.user.id
                if target_id == user_id: continue
                
                is_target_afk, data = await db.is_afk(target_id)
                if is_target_afk:
                     afk_time = int(time.time() - data["time"])
                     seen_ago = get_readable_time(afk_time)
                     reason = data.get("reason")
                     text = f"{entity.user.mention} is AFK.\nTime: {seen_ago}"
                     if reason: text += f"\nReason: {reason}"
                     await message.reply_text(text)
                     break
