import os
import httpx
from pyrogram import filters
from pyrogram.types import Message

from bot import app
from bot.helpers.feds_utils import capture_err

__MODULE__ = "OCR"
__HELP__ = "/ocr [reply to photo] - Read Text From Image"


@app.on_message(filters.command("ocr") & filters.group)
@capture_err
async def ocr_cmd(client, message: Message):
    reply = message.reply_to_message
    if (
        not reply
        or (not reply.sticker and not reply.photo and not reply.document)
    ):
        return await message.reply_text("Reply to a photo, sticker, or image document to extract text.")

    # Validation for document mime type
    if reply.document and not reply.document.mime_type.startswith("image"):
        return await message.reply_text("Reply to a valid image file.")

    msg = await message.reply_text("Processing image...")
    file_path = None
    try:
        file_path = await reply.download()
        
        # ImgBB Upload
        async with httpx.AsyncClient() as http:
            # Upload to ImgBB (unofficial/scraped endpoint usage from MissKaty)
            # A more robust way would be to use a public key or another host, but porting logic as is.
            imgbb_url = "https://imgbb.com/json"
            headers = {
                "origin": "https://imgbb.com",
                "referer": "https://imgbb.com/upload",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
            }
            
            # Prepare file for upload
            with open(file_path, "rb") as f:
                files = {"source": ("image.jpg", f, "image/jpeg")}
                data = {"type": "file", "action": "upload"}
                
                response = await http.post(imgbb_url, data=data, files=files, headers=headers)
                resp_json = response.json()
                
            if "image" not in resp_json:
                 raise Exception("Failed to upload image to ImgBB.")
                 
            image_url = resp_json["image"]["url"]
            
            # Google Script OCR
            google_script_url = f"https://script.google.com/macros/s/AKfycbwURISN0wjazeJTMHTPAtxkrZTWTpsWIef5kxqVGoXqnrzdLdIQIfLO7jsR5OQ5GO16/exec?url={image_url}"
            
            ocr_resp = await http.get(google_script_url, follow_redirects=True)
            ocr_json = ocr_resp.json()
            
            if "text" in ocr_json:
                text = ocr_json["text"]
                if not text:
                    await msg.edit("No text detected.")
                else:
                    await msg.edit(f"**OCR Result:**\n\n`{text}`")
            else:
                 await msg.edit("Failed to extract text from API response.")

    except Exception as e:
        await msg.edit(f"Error: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
