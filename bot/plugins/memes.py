import os
import textwrap
import asyncio
from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters
from bot import app
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Memes"
__HELP__ = """
<b>Memes:</b>
/memify <text> [size] - Reply to a sticker/photo to add text. Use `;` to split top/bottom text.
/mmf <text> [size] - Same as memify.

<b>Size options:</b> small, medium, large, or custom number (e.g., 80)
<b>Example:</b> <code>/mmf Top;Bottom large</code>
"""

async def draw_meme_text(image_path, text, font_size_option="large"):
    img = Image.open(image_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
        
    i_width, i_height = img.size
    
    # Font handling
    font_path = "assets/impact.ttf"
    if not os.path.exists(font_path):
        # Fallback to system font
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if not os.path.exists(font_path):
             font_path = None # Default
             
    if font_path:
        # Determine font size based on user preference
        size_presets = {
            "small": (150 / 640, 40),    # ratio, minimum
            "medium": (200 / 640, 50),
            "large": (250 / 640, 60),
        }
        
        # Check if it's a preset or custom number
        if font_size_option.lower() in size_presets:
            ratio, min_size = size_presets[font_size_option.lower()]
            font_size = int(ratio * i_width)
            font_size = max(min_size, font_size)
        else:
            # Try to parse as custom pixel value
            try:
                font_size = int(font_size_option)
                font_size = max(20, min(500, font_size))  # Clamp between 20-500px
            except ValueError:
                # Default to large if invalid
                font_size = int((250 / 640) * i_width)
                font_size = max(60, font_size)
        
        m_font = ImageFont.truetype(font_path, font_size)
    else:
        m_font = ImageFont.load_default()

    if ";" in text:
        upper_text, lower_text = text.split(";", 1)
    else:
        upper_text = text
        lower_text = ""

    draw = ImageDraw.Draw(img)
    
    def draw_text_with_outline(text, position, font):
        x, y = position
        # Draw outline
        outline_range = 3
        for adj in range(-outline_range, outline_range+1):
             for adj2 in range(-outline_range, outline_range+1):
                  draw.text((x+adj, y+adj2), text, font=font, fill="black")
        # Draw text
        draw.text((x, y), text, font=font, fill="white")

    # Draw Upper Text
    current_h = 10
    if upper_text:
        lines = textwrap.wrap(upper_text, width=15)
        for line in lines:
            bbox = m_font.getbbox(line)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (i_width - w) / 2
            y = current_h
            
            draw_text_with_outline(line, (x, y), m_font)
            current_h += h + 5

    # Draw Lower Text
    current_h = i_height - 20 # Start from bottom
    if lower_text:
        lines = textwrap.wrap(lower_text, width=15)
        # Calculate total height to position correctly
        total_h = 0
        line_heights = []
        for line in lines:
             bbox = m_font.getbbox(line)
             h = bbox[3] - bbox[1]
             total_h += h + 5
             line_heights.append(h)
             
        current_y = i_height - total_h - 10
        
        for i, line in enumerate(lines):
             bbox = m_font.getbbox(line)
             w = bbox[2] - bbox[0]
             x = (i_width - w) / 2
             
             draw_text_with_outline(line, (x, current_y), m_font)
             current_y += line_heights[i] + 5

    output_path = "meme.webp"
    img.save(output_path, "WEBP")
    return output_path

@app.on_message(filters.command(["memify", "mmf"]) & filters.group)
@capture_err
async def memify_cmd(client, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a sticker or photo.")
        
    reply = message.reply_to_message
    
    if not (reply.sticker or reply.photo):
         return await message.reply_text("Reply to a sticker or photo.")
         
    if len(message.command) < 2:
         return await message.reply_text(
             "Provide text! Usage: <code>/mmf Top Text;Bottom Text [size]</code>\n"
             "Size: small, medium, large, or number (e.g., 80)"
         )
    
    # Parse text and optional size
    args = message.text.split(None, 1)[1]
    
    # Check if last word is a size option
    parts = args.rsplit(None, 1)
    if len(parts) == 2 and (parts[1].lower() in ["small", "medium", "large"] or parts[1].isdigit()):
        text = parts[0]
        size_option = parts[1]
    else:
        text = args
        size_option = "large"  # default
    
    msg = await message.reply_text("Processing meme...")
    
    try:
        file_path = await reply.download()
        output = await draw_meme_text(file_path, text, size_option)
        
        await message.reply_sticker(output)
        
        os.remove(file_path)
        os.remove(output)
        await msg.delete()
        
    except Exception as e:
        await msg.edit(f"Error: {e}")
