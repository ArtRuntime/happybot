import asyncio
import httpx
from pyrogram import filters, enums
from pyrogram.types import Message


from bot import app
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Games"
__HELP__ = """
<b>Games:</b>
Play simple games in the group.

/guessimg - Guess the image.
/riddle - Guess the riddle (Lontong style).
/wordgame - Guess the word.
/riddlegame - Guess the riddle.
/stopgame - Stop the current game.
"""

# Store game state per chat: {chat_id: {"active": bool, "answer": str}}
GAME_STATUS = {}

GAME_MODES = {
    "guessimg": {
        "url": "https://yasirapi.eu.org/tebakgambar",
        "type": "image",
        "response_key": "img",
        "answer_key": "jawaban"
    },
    "riddle": {
        "url": "https://yasirapi.eu.org/tebaklontong",
        "type": "text",
        "response_key": "soal",
        "answer_key": "jawaban",
        "description_key": "deskripsi"
    },
    "wordgame": {
        "url": "https://yasirapi.eu.org/tebakkata",
        "type": "text",
        "response_key": "soal",
        "answer_key": "jawaban"
    },
    "riddlegame": {
        "url": "https://yasirapi.eu.org/tebaktebakan",
        "type": "text",
        "response_key": "soal",
        "answer_key": "jawaban"
    }
}

async def play_game(client, message, mode):
    chat_id = message.chat.id
    if GAME_STATUS.get(chat_id, {}).get("active"):
        return await message.reply_text("A game is already running in this chat. Finish it or /stopgame.")

    mode_data = GAME_MODES[mode]
    
    async with httpx.AsyncClient() as http:
        try:
            resp = await http.get(mode_data["url"], timeout=10.0)
            if resp.status_code != 200:
                return await message.reply_text("Failed to fetch game data.")
            data = resp.json()
        except Exception:
            return await message.reply_text("API Error.")

    answer = data.get(mode_data["answer_key"])
    if not answer:
        return await message.reply_text("Error parsing game data.")
        
    GAME_STATUS[chat_id] = {"active": True, "answer": answer.lower()}

    # Send Question
    if mode_data["type"] == "image":
        img_url = data.get(mode_data["response_key"])
        await message.reply_photo(img_url, caption="Guess this image! You have 60 seconds.")
    else:
        question = data.get(mode_data["response_key"])
        await message.reply_text(f"<b>Question:</b>\n{question}\n\nYou have 60 seconds.")

    # Listen for answer
    # Note: app.listen is not standard pyrogram. But I can implement a loop or use a handler approach.
    # MissKaty uses client.listen(chat_id, filters, timeout). 
    # HappyBot might not have client.listen unless userbot has it or I implement it.
    # Standard Pyrogram doesn't have listen. 
    # I'll implement a simple wait_for_message loop or a conversation handler if I had one.
    # BUT, since I can't block the thread easily with wait_for without convenience method, 
    # I'll enable a handler and use a timeout task.
    
    # Wait, `client.listen` is a convenience method often added by `pyromod` or custom `Client`.
    # I'll assume HappyBot DOES NOT have `listen`.
    # I'll use a global handler that checks `GAME_STATUS`.
    
    # Actually, without `listen`, I have to rely on `on_message` handler to check every message.
    # `game_check_handler` below handles the checking.
    
    # But how to handle timeout?
    # I'll use asyncio.sleep(60) and check if still active.
    
    await asyncio.sleep(60)
    
    status = GAME_STATUS.get(chat_id)
    if status and status["active"] and status["answer"] == answer.lower():
        # Clean up if still active (timeout)
        del GAME_STATUS[chat_id]
        text = f"Time's up! The answer was: <b>{answer}</b>"
        if "description_key" in mode_data and mode_data["description_key"] in data:
            text += f"\nReason: {data[mode_data['description_key']]}"
        await client.send_message(chat_id, text)



# Command aliases: old Indonesian names → new English names
COMMAND_ALIASES = {
    "tebakgambar": "guessimg",
    "tebaklontong": "riddle",
    "tebakkata": "wordgame",
    "tebaktebakan": "riddlegame"
}

@app.on_message(filters.command(["guessimg", "riddle", "wordgame", "riddlegame", "tebakgambar", "tebaklontong", "tebakkata", "tebaktebakan"]) & filters.group)
@capture_err
async def game_cmd(client, message):
    cmd = message.command[0]
    # Translate old command to new if needed
    cmd = COMMAND_ALIASES.get(cmd, cmd)
    await play_game(client, message, cmd)


@app.on_message(filters.command("stopgame") & filters.group)
async def stop_game(client, message):
    chat_id = message.chat.id
    if GAME_STATUS.get(chat_id, {}).get("active"):
        del GAME_STATUS[chat_id]
        await message.reply_text("Game stopped.")
    else:
        await message.reply_text("No active game.")

@app.on_message(filters.group & ~filters.bot, group=70)
async def check_answer(client, message):
    chat_id = message.chat.id
    status = GAME_STATUS.get(chat_id)
    
    if not status or not status["active"]:
        return
        
    if message.text and message.text.lower() == status["answer"]:
        del GAME_STATUS[chat_id]
        await message.reply_text(f"🎉 Correct! <b>{message.from_user.first_name}</b> guessed it!\nAnswer: <b>{status['answer'].upper()}</b>")
    
    # Hint logic? Nah.
