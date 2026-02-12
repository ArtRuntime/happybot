import asyncio
import os
import re
import shutil
import tempfile
import emoji

from PIL import Image
from pyrogram import Client, filters, enums
from pyrogram.errors import BadRequest, PeerIdInvalid, StickersetInvalid
from pyrogram.file_id import FileId
from pyrogram.raw.functions.messages import GetStickerSet, SendMedia
from pyrogram.raw.functions.stickers import (
    AddStickerToSet,
    CreateStickerSet,
    RemoveStickerFromSet,
)
from pyrogram.raw.types import (
    DocumentAttributeFilename,
    InputDocument,
    InputMediaUploadedDocument,
    InputStickerSetItem,
    InputStickerSetShortName,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import app, config
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Stickers"
__HELP__ = """
**Sticker Commands:**

/kang [Reply to sticker/image] - Add sticker to your pack.
/unkang [Reply to sticker] - Remove sticker from your pack.
/getsticker - Convert sticker to PNG.
/stickerid - Get sticker ID.
"""

def get_emoji_regex():
    # Compatible with emoji >= 2.0.0
    if hasattr(emoji, "EMOJI_DATA"):
        e_list = list(emoji.EMOJI_DATA.keys())
    else:
        # Fallback for older versions (unlikely but safe)
        e_list = [
            getattr(emoji, e).encode("unicode-escape").decode("ASCII")
            for e in dir(emoji)
            if not e.startswith("_") and not e.startswith("*")
        ]
    # Sort by length to match longest emoji first (greedy match)
    e_sort = sorted(e_list, key=len, reverse=True)
    pattern_ = f"({'|'.join(re.escape(e) for e in e_sort)})"
    return re.compile(pattern_)

EMOJI_PATTERN = get_emoji_regex()

def resize_image(filename: str) -> str:
    im = Image.open(filename)
    maxsize = 512
    scale = maxsize / max(im.width, im.height)
    sizenew = (int(im.width * scale), int(im.height * scale))
    im = im.resize(sizenew, Image.NEAREST)
    downpath, f_name = os.path.split(filename)
    png_image = os.path.join(downpath, f"{f_name.split('.', 1)[0]}.png")
    im.save(png_image, "PNG")
    if png_image != filename:
        os.remove(filename)
    return png_image

async def convert_video(filename: str) -> str:
    downpath, f_name = os.path.split(filename)
    webm_video = os.path.join(downpath, f"{f_name.split('.', 1)[0]}.webm")
    cmd = [
        "ffmpeg", "-loglevel", "quiet", "-i", filename,
        "-t", "00:00:03", "-vf", "fps=30,scale=512:512", # Force scale ensuring fit? MissKaty uses direct scaling
        "-c:v", "libvpx-vp9", "-b:v", "256k", # MissKaty used vp9 and 500k, adjusting for safety
        "-an", "-y", webm_video
    ]
    # MissKaty command was:
    # ffmpeg -loglevel quiet -i filename -t 00:00:03 -vf fps=30 -c:v vp9 -b:v: 500k -preset ultrafast -s 512x512 -y -an webm_video
    # I'll stick to a closer version of that
    cmd = [
        "ffmpeg", "-loglevel", "quiet", "-i", filename, "-t", "00:00:03",
        "-vf", "fps=30,scale=512:512", "-c:v", "libvpx-vp9", "-b:v", "500k",
        "-preset", "ultrafast", "-y", "-an", webm_video
    ]

    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()

    if webm_video != filename:
        if os.path.exists(filename):
            os.remove(filename)
    return webm_video

@app.on_message(filters.command(["getsticker", "toimage"]) & filters.group)
@capture_err
async def getsticker_(client, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a sticker.")
        
    sticker = message.reply_to_message.sticker
    if not sticker:
        return await message.reply_text("Reply to a sticker.")
        
    if sticker.is_animated:
        return await message.reply_text("Animated stickers are not supported yet for this command.")
        
    with tempfile.TemporaryDirectory() as tempdir:
        path = os.path.join(tempdir, "getsticker")
        sticker_file = await client.download_media(
            message=message.reply_to_message,
            file_name=f"{path}/{sticker.set_name}.png",
        )
        await message.reply_document(
            document=sticker_file,
            caption=f"**Emoji:** {sticker.emoji}\n**Sticker ID:** `{sticker.file_id}`"
        )

@app.on_message(filters.command("stickerid") & filters.group)
@capture_err
async def getstickerid(client, message):
    if message.reply_to_message and message.reply_to_message.sticker:
        await message.reply_text(f"Sticker ID: `{message.reply_to_message.sticker.file_id}`")
    else:
        await message.reply_text("Reply to a sticker.")

@app.on_message(filters.command("unkang") & filters.group)
@capture_err
async def unkang(client, message):
    if not message.reply_to_message or not message.reply_to_message.sticker:
        return await message.reply_text("Reply to a sticker to remove it.")
        
    sticker = message.reply_to_message.sticker
    user = message.from_user
    
    if str(user.id) not in sticker.set_name:
        return await message.reply_text("You can only remove stickers from your own packs created by this bot.")
        
    msg = await message.reply_text("Removing sticker...")
    try:
        decoded = FileId.decode(sticker.file_id)
        sticker_input = InputDocument(
            id=decoded.media_id,
            access_hash=decoded.access_hash,
            file_reference=decoded.file_reference,
        )
        await client.invoke(RemoveStickerFromSet(sticker=sticker_input))
        await msg.edit("Sticker removed from pack.")
    except Exception as e:
        await msg.edit(f"Error: {e}")


@app.on_message(filters.command(["kang", "steal"]) & filters.group)
@capture_err
async def kang_sticker(client, message):
    if not message.from_user:
        return
        
    prog_msg = await message.reply_text("Kanging sticker...")
    sticker_emoji = "🤔"
    packnum = 0
    packname_found = False
    resize = False
    animated = False
    videos = False
    convert = False
    reply = message.reply_to_message
    user_id = message.from_user.id
    username = client.me.username

    if reply and reply.media:
        if reply.photo:
            resize = True
        elif reply.animation:
            videos = True
            convert = True
        elif reply.video:
            convert = True
            videos = True
        elif reply.document:
            if "image" in reply.document.mime_type:
                resize = True
            elif reply.document.mime_type in (enums.MessageMediaType.VIDEO, enums.MessageMediaType.ANIMATION):
                videos = True
                convert = True
            elif "tgsticker" in reply.document.mime_type:
                animated = True
        elif reply.sticker:
            if not reply.sticker.file_name:
                 return await prog_msg.edit("Sticker has no filename.")
            if reply.sticker.emoji:
                sticker_emoji = reply.sticker.emoji
            animated = reply.sticker.is_animated
            videos = reply.sticker.is_video
            if videos:
                convert = False
            elif not reply.sticker.file_name.endswith(".tgs"):
                resize = True
        else:
            return await prog_msg.edit("Unsupported media type.")
            
        pack_prefix = "anim" if animated else "vid" if videos else "a"
        packname = f"{pack_prefix}_{user_id}_by_{username}"
        
        # Handle arguments
        args = message.command[1:]
        if args and args[0].isdigit() and int(args[0]) > 0:
            packnum = int(args.pop(0))
            packname = f"{pack_prefix}{packnum}_{user_id}_by_{username}"
            
        if args:
             sticker_emoji = "".join(set(EMOJI_PATTERN.findall("".join(args)))) or sticker_emoji

        filename = await client.download_media(reply)
        if not filename:
            return await prog_msg.edit("Failed to download media.")
            
    else:
        return await prog_msg.edit("Reply to media to kang.")
        
    try:
        if resize:
            filename = resize_image(filename)
        elif convert:
            filename = await convert_video(filename)
            
        max_stickers = 50 if animated else 120
        
        while not packname_found:
            try:
                stickerset = await client.invoke(
                    GetStickerSet(
                        stickerset=InputStickerSetShortName(short_name=packname),
                        hash=0,
                    )
                )
                if stickerset.set.count >= max_stickers:
                    packnum += 1
                    packname = f"{pack_prefix}_{packnum}_{user_id}_by_{username}"
                else:
                    packname_found = True
            except StickersetInvalid:
                break
                
        # Upload file
        # Using a dummy message to upload is tricky without send_document/send_message
        # MissKaty uses a raw SendMedia to LOG_CHANNEL.
        # We can use client.save_file ? No, save_file returns InputFile, but we need InputDocument for stickers?
        # Actually pyrogram's save_file returns InputFile.
        # MissKaty logic:
        # file = await self.save_file(filename) -> Returns InputFile
        # media = await self.invoke(SendMedia(..., media=InputMediaUploadedDocument(file=file, ...)))
        # This creates a message with document, which we then get the Document object from.
        # 
        # Simpler approach:
        # Send document to config.LOGGER_ID, extract document, then use it.
        
        if not config.LOGGER_ID:
            return await prog_msg.edit("Logger ID not set. Cannot kang.")
            
        uploaded_msg = await client.send_document(
            config.LOGGER_ID,
            document=filename,
            force_document=True,
            caption=f"#Sticker kang by {user_id}"
        )
        stkr_file = uploaded_msg.document
        
        if packname_found:
            await prog_msg.edit("Adding to existing pack...")
            await client.invoke(
                AddStickerToSet(
                    stickerset=InputStickerSetShortName(short_name=packname),
                    sticker=InputStickerSetItem(
                        document=InputDocument(
                            id=stkr_file.file_id, # Pyrogram Document object has file_id as str? 
                            # Wait, InputDocument needs id (int), access_hash (int), file_reference (bytes)
                            # Pyrogram Document.file_id is a file_id string.
                            # We need to decode it or use raw object if available?
                            # uploaded_msg.document IS a pyrogram type.
                            # We can use FileId.decode(stkr_file.file_id)
                        ),
                        emoji=sticker_emoji,
                    ),
                )
            )
            # WAIT: InputDocument requires raw ID. 
            # `stkr_file` from `send_document` is a Pyrogram Object.
            # We need to decode `stkr_file.file_id`.
            
            decoded = FileId.decode(stkr_file.file_id)
            input_doc = InputDocument(
                id=decoded.media_id,
                access_hash=decoded.access_hash,
                file_reference=decoded.file_reference,
            )
            
            await client.invoke(
                AddStickerToSet(
                    stickerset=InputStickerSetShortName(short_name=packname),
                    sticker=InputStickerSetItem(
                        document=input_doc,
                        emoji=sticker_emoji,
                    ),
                )
            )
        else:
            await prog_msg.edit("Creating new pack...")
            stkr_title = f"{message.from_user.first_name}'s"
            if animated:
                stkr_title += " AnimPack"
            elif videos:
                stkr_title += " VidPack"
            if packnum != 0:
                stkr_title += f" v{packnum}"
                
            user_peer = await client.resolve_peer(user_id)
            
            decoded = FileId.decode(stkr_file.file_id)
            input_doc = InputDocument(
                id=decoded.media_id,
                access_hash=decoded.access_hash,
                file_reference=decoded.file_reference,
            )
            
            await client.invoke(
                CreateStickerSet(
                    user_id=user_peer,
                    title=stkr_title,
                    short_name=packname,
                    stickers=[
                        InputStickerSetItem(
                            document=input_doc,
                            emoji=sticker_emoji,
                        )
                    ],
                )
            )
            
        await prog_msg.edit(
            f"Sticker kanged to [pack](https://t.me/addstickers/{packname})!",
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await prog_msg.edit(f"Error: {e}")
        
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)

