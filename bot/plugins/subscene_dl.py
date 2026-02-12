import os
import asyncio
from pyrogram import filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot import app
from bot.helpers.feds_utils import capture_err, split_arr
from bot.helpers.subscene import search_sub, get_sub_options, down_page, download_file

__MODULE__ = "Subscene"
__HELP__ = "/subscene <title> - Search and download subtitles."

# In-memory storage for search results (per message ID)
SUB_TITLE_DICT = {}
SUB_DL_DICT = {}

@app.on_message(filters.command("subscene") & filters.group)
@capture_err
async def subscene_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"Usage: /subscene <Movie/Series Name>")
        
    query = " ".join(message.command[1:])
    msg = await message.reply_text("⏳ Searching Subscene...")
    
    results = await search_sub(query)
    if not results:
        return await msg.edit("No results found.")
        
    # Store results
    SUB_TITLE_DICT[msg.id] = {
        "results": split_arr(results, 10),
        "query": query,
        "user_id": message.from_user.id
    }
    
    await show_title_results(msg, 1)


async def show_title_results(message, page):
    data = SUB_TITLE_DICT.get(message.id)
    if not data:
        return
        
    results_pages = data["results"]
    total_pages = len(results_pages)
    current_page_index = page - 1
    
    if current_page_index >= total_pages:
        return

    current_results = results_pages[current_page_index]
    
    text = f"**Subscene Search Results for:** `{data['query']}`\n\n"
    buttons = []
    
    for i, res in enumerate(current_results):
        idx = (current_page_index * 10) + i + 1
        text += f"{idx}. [{res['title']}]({res['link']})\n"
        buttons.append(InlineKeyboardButton(str(idx), callback_data=f"sublist#{page}#{i}#{message.id}"))
        
    # Pagination Buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"subscenepage#{page-1}#{message.id}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"subscenepage#{page+1}#{message.id}"))
    
    rows = []
    # Chunk item buttons
    for i in range(0, len(buttons), 5):
        rows.append(buttons[i:i+5])
        
    if nav_buttons:
        rows.append(nav_buttons)
        
    rows.append([InlineKeyboardButton("❌ Close", callback_data=f"close#{data['user_id']}")])

    await message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(rows),
        disable_web_page_preview=True
    )


@app.on_callback_query(filters.regex(r"^subscenepage#"))
async def subscene_page(client, cb):
    _, page, msg_id = cb.data.split("#")
    page = int(page)
    msg_id = int(msg_id)
    
    data = SUB_TITLE_DICT.get(msg_id)
    if not data:
         await cb.answer("Session expired. Search again.", show_alert=True)
         return
         
    if cb.from_user.id != data["user_id"]:
        return await cb.answer("Not your search.", show_alert=True)
        
    await show_title_results(cb.message, page)
    await cb.answer()


@app.on_callback_query(filters.regex(r"^sublist#"))
async def sublist_callback(client, cb):
    _, page, index, msg_id = cb.data.split("#")
    page = int(page)
    index = int(index)
    msg_id = int(msg_id)
    
    data = SUB_TITLE_DICT.get(msg_id)
    if not data:
        await cb.answer("Session expired.", show_alert=True)
        return

    if cb.from_user.id != data["user_id"]:
        return await cb.answer("Not your search.", show_alert=True)

    selected_item = data["results"][page-1][index]
    link = selected_item["link"]
    
    # Store selected movie link and fetch options
    await cb.message.edit("Fetching subtitles...")
    
    sub_options = await get_sub_options(link)
    if not sub_options:
         await cb.message.edit("No subtitles found or error fetching.")
         return
         
    SUB_DL_DICT[msg_id] = {
        "results": split_arr(sub_options, 10),
        "link": link,
        "user_id": cb.from_user.id
    }
    
    await show_sub_options(cb.message, 1)


async def show_sub_options(message, page):
    data = SUB_DL_DICT.get(message.id)
    if not data:
        return
        
    results_pages = data["results"]
    total_pages = len(results_pages)
    current_page_index = page - 1
    
    current_results = results_pages[current_page_index]
    
    text = f"**Subtitles for:** [Link]({data['link']})\n\n"
    buttons = []
    
    for i, res in enumerate(current_results):
        idx = (current_page_index * 10) + i + 1
        text += f"{idx}. {res['lang']} - {res['title']} {res['rate']}\n"
        buttons.append(InlineKeyboardButton(str(idx), callback_data=f"dlsub#{page}#{i}#{message.id}"))
        
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"subdlpage#{page-1}#{message.id}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"subdlpage#{page+1}#{message.id}"))
        
    rows = []
    for i in range(0, len(buttons), 5):
        rows.append(buttons[i:i+5])
        
    if nav_buttons:
        rows.append(nav_buttons)
        
    rows.append([InlineKeyboardButton("❌ Close", callback_data=f"close#{data['user_id']}")]) # Re-use user_id from clicker? No, stored
    
    await message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(rows),
        disable_web_page_preview=True
    )


@app.on_callback_query(filters.regex(r"^subdlpage#"))
async def subdl_page(client, cb):
    _, page, msg_id = cb.data.split("#")
    page = int(page)
    msg_id = int(msg_id)
    
    data = SUB_DL_DICT.get(msg_id)
    if not data:
         await cb.answer("Session expired.", show_alert=True)
         return
         
    if cb.from_user.id != data["user_id"]:
        return await cb.answer("Not your search.", show_alert=True)
        
    await show_sub_options(cb.message, page)
    await cb.answer()


@app.on_callback_query(filters.regex(r"^dlsub#"))
async def dlsub_callback(client, cb):
    _, page, index, msg_id = cb.data.split("#")
    page = int(page)
    index = int(index)
    msg_id = int(msg_id)
    
    data = SUB_DL_DICT.get(msg_id)
    if not data:
         await cb.answer("Session expired.", show_alert=True)
         return
         
    if cb.from_user.id != data["user_id"]:
        return await cb.answer("Not your search.", show_alert=True)

    selected_sub = data["results"][page-1][index]
    link = selected_sub["link"]
    title = selected_sub["title"]
    
    await cb.message.edit(f"Downloading {title}...")
    
    try:
        page_info = await down_page(link)
        if not page_info or not page_info["download_url"]:
            return await cb.message.edit("Failed to retrieve download link.")
            
        dl_url = page_info["download_url"]
        filename = f"{title}.zip"
        
        await download_file(dl_url, filename)
        
        caption = f"**Title:** {page_info['title']}\n**Author:** {page_info['author_name']}\n**Release:**\n{page_info['releases']}"
        
        await cb.message.reply_document(
            document=filename,
            caption=caption
        )
        
        os.remove(filename)
        await cb.message.delete()
        
    except Exception as e:
        await cb.message.edit(f"Error: {e}") 
        if os.path.exists(filename):
            os.remove(filename)


@app.on_callback_query(filters.regex(r"^close#"))
async def close_cb(client, cb):
    _, user_id = cb.data.split("#")
    if cb.from_user.id != int(user_id):
        return await cb.answer("Not yours.", show_alert=True)
    await cb.message.delete()
