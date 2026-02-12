import os
import httpx
from pyrogram import filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot import app
from bot.helpers.feds_utils import capture_err
from bot.helpers.tools import rentry, post_to_telegraph

__MODULE__ = "DevTools"
__HELP__ = """
**Developer Tools:**

/paste <text/reply> - Paste text to Pasty/Spacebin.
/rentry <text/reply> - Paste to Rentry.co.
/neko <text/reply> - Paste to Nekobin.
/tgraph <text/reply> - Post to Telegraph.
/imgbb <reply photo> - Upload to ImgBB.
/pypi <package> - Search PyPI packages.
"""

async def get_text(message):
    if message.reply_to_message:
        if message.reply_to_message.document:
            file_path = await message.reply_to_message.download()
            with open(file_path, "r") as f:
                text = f.read()
            os.remove(file_path)
            return text
        else:
            return message.reply_to_message.text or message.reply_to_message.caption
    elif len(message.command) > 1:
        return message.text.split(None, 1)[1]
    return None

@app.on_message(filters.command("rentry") & filters.group)
@capture_err
async def rentry_cmd(client, message):
    text = await get_text(message)
    if not text:
        return await message.reply_text("Provide text or reply to a message.")
        
    msg = await message.reply_text("Pasting to Rentry...")
    url = await rentry(text)
    
    if url:
        await msg.edit(f"**Pasted to Rentry:** [Link]({url})", disable_web_page_preview=True)
    else:
        await msg.edit("Failed to paste to Rentry.")

@app.on_message(filters.command("tgraph") & filters.group)
@capture_err
async def tgraph_cmd(client, message):
    text = await get_text(message)
    if not text:
        return await message.reply_text("Provide text or reply to a message.")
        
    msg = await message.reply_text("Posting to Telegraph...")
    title = f"Paste by {message.from_user.first_name}"
    url = await post_to_telegraph(title, text)
    
    if url:
        await msg.edit(f"**Posted to Telegraph:** [Link]({url})", disable_web_page_preview=True)
    else:
        await msg.edit("Failed to post to Telegraph.")

@app.on_message(filters.command("neko") & filters.group)
@capture_err
async def neko_cmd(client, message):
    text = await get_text(message)
    if not text:
        return await message.reply_text("Provide text or reply to a message.")
        
    msg = await message.reply_text("Pasting to Nekobin...")
    
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post("https://nekobin.com/api/documents", json={"content": text})
            key = resp.json()["result"]["key"]
            url = f"https://nekobin.com/{key}"
            await msg.edit(f"**Pasted to Nekobin:** [Link]({url})", disable_web_page_preview=True)
    except Exception as e:
        await msg.edit(f"Error: {e}")

@app.on_message(filters.command(["paste", "sbin"]) & filters.group)
@capture_err
async def paste_cmd(client, message):
    text = await get_text(message)
    if not text:
        return await message.reply_text("Provide text or reply to a message.")
        
    msg = await message.reply_text("Pasting to Spacebin...")
    
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post("https://spaceb.in/api/", json={"content": text, "extension": "txt"})
            res_json = resp.json()
            if "payload" in res_json:
                url = f"https://spaceb.in/{res_json['payload']['id']}"
                await msg.edit(f"**Pasted to Spacebin:** [Link]({url})", disable_web_page_preview=True)
            else:
                 await msg.edit("Failed to paste to Spacebin.")
    except Exception as e:
        await msg.edit(f"Error: {e}")

@app.on_message(filters.command("imgbb") & filters.group)
@capture_err
async def imgbb_cmd(client, message):
    reply = message.reply_to_message
    if not reply or (not reply.photo and not reply.document):
        return await message.reply_text("Reply to an image.")
        
    msg = await message.reply_text("Uploading to ImgBB...")
    
    try:
        path = await reply.download()
        async with httpx.AsyncClient() as http:
            with open(path, "rb") as f:
                files = {"source": f}
                data = {"type": "file", "action": "upload"}
                # Using scraped endpoint from MissKaty
                resp = await http.post(
                    "https://imgbb.com/json", 
                    data=data, 
                    files=files,
                    headers={"Referer": "https://imgbb.com/"}
                )
                res_json = resp.json()
                if "image" in res_json:
                    url = res_json["image"]["url"]
                    await msg.edit(f"**Uploaded to ImgBB:** [Link]({url})", disable_web_page_preview=True)
                else:
                    await msg.edit("Failed to upload.")
        os.remove(path)
    except Exception as e:
        await msg.edit(f"Error: {e}")

@app.on_message(filters.command("pypi") & filters.group)
@capture_err
async def pypi_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /pypi <package_name>")
        
    package = message.command[1]
    msg = await message.reply_text(f"Searching for {package}...")
    
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"https://pypi.org/pypi/{package}/json")
            
        if resp.status_code != 200:
            return await msg.edit("Package not found.")
            
        data = resp.json()
        info = data["info"]
        
        name = info.get("name", "Unknown")
        version = info.get("version", "Unknown")
        summary = info.get("summary", "No description")
        home_page = info.get("home_page", "")
        author = info.get("author", "Unknown")
        license = info.get("license", "Unknown")
        
        text = f"**Package:** `{name}`\n"
        text += f"**Version:** `{version}`\n"
        text += f"**Author:** {author}\n"
        text += f"**License:** {license}\n"
        text += f"**Summary:** {summary}\n"
        text += f"**Pip:** `pip install {name}`"
        
        buttons = []
        if home_page:
            buttons.append([InlineKeyboardButton("Home Page", url=home_page)])
        if info.get("project_urls") and "Documentation" in info["project_urls"]:
            buttons.append([InlineKeyboardButton("Documentation", url=info["project_urls"]["Documentation"])])
            
        await msg.edit(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
        
    except Exception as e:
        await msg.edit(f"Error: {e}")
