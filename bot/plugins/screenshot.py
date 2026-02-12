import os
import time
import httpx
import tempfile
from pyrogram import filters, enums
from pyrogram.types import Message

from bot import app
from bot.helpers.feds_utils import capture_err, take_ss

__MODULE__ = "Screenshots"
__HELP__ = """
**Screenshot Commands:**

/webss <url> - Take a screenshot of a webpage.
/genss <reply/url> - Generate a screenshot from a video.
"""

@app.on_message(filters.command("webss") & filters.group)
@capture_err
async def webss_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage Box: /webss <url>")
        
    url = message.command[1]
    if not url.startswith("http"):
        url = "https://" + url
        
    msg = await message.reply_text("Taking screenshot...")
    
    api_url = f"https://webss.yasirweb.eu.org/api/screenshot?resX=1280&resY=900&outFormat=jpg&waitTime=1000&isFullPage=false&dismissModals=false&url={url}"
    
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            response = await http.get(api_url)
            
        if response.status_code != 200:
             return await msg.edit("Failed to get screenshot from API.")
             
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(response.content)
            temp_file = tf.name
            
        await message.reply_photo(
            photo=temp_file,
            caption=f"Screenshot of {url}"
        )
        await msg.delete()
        os.remove(temp_file)
        
    except Exception as e:
        await msg.edit(f"Error: {e}")


@app.on_message(filters.command("genss") & filters.group)
@capture_err
async def genss_cmd(client, message):
    reply = message.reply_to_message
    url = None
    media = None
    
    if len(message.command) > 1:
        url = message.command[1]
    elif reply:
        if reply.video:
            media = reply.video
        elif reply.document and reply.document.mime_type.startswith("video"):
            media = reply.document
        elif reply.animation:
            media = reply.animation
            
    if not url and not media:
        return await message.reply_text("Provide a URL or reply to a video.")
        
    msg = await message.reply_text("Processing...")
    temp_video = None
    
    try:
        with tempfile.TemporaryDirectory() as tempdir:
            if url:
                # Download form URL
                temp_video = os.path.join(tempdir, "video.mp4")
                async with httpx.AsyncClient(timeout=30) as http:
                    async with http.stream("GET", url) as resp:
                        if resp.status_code != 200:
                            return await msg.edit("Failed to download video.")
                        with open(temp_video, "wb") as f:
                             async for chunk in resp.aiter_bytes():
                                 f.write(chunk)
            else:
                # Download from Telegram
                temp_video = await client.download_media(media, file_name=os.path.join(tempdir, "video.mp4"))
                
            if not temp_video or not os.path.exists(temp_video):
                 return await msg.edit("Failed to download/locate video.")
                 
            # Take screenshot
            ss_path = os.path.join(tempdir, "ss.jpg")
            result = await take_ss(temp_video, ss_path)
            
            if result:
                await message.reply_photo(result, caption="Video Screenshot")
                await msg.delete()
            else:
                await msg.edit("Failed to generate screenshot.")
                
    except Exception as e:
        await msg.edit(f"Error: {e}")
