import httpx
from pyrogram import filters, enums
from bot import app
from bot.helpers.feds_utils import capture_err
from bot.helpers.tools import rentry

__MODULE__ = "CodeRunner"
__HELP__ = """
**Code Runner:**
Run code snippets via Glot.io API.

**Commands:**
/python, /cpp, /c, /java, /js, /php, /go, /rust, /ruby, /lua, /bash, etc.

Usage: 
/python `print("Hello World")`
"""

GLOT_TOKEN = "b8a2b75a-a078-4089-869c-e53d448b1ebb"

LANGUAGES = {
    "python": ("python", "py"),
    "cpp": ("cpp", "cpp"),
    "c": ("c", "c"),
    "java": ("java", "java"),
    "javascript": ("javascript", "js"),
    "js": ("javascript", "js"),
    "php": ("php", "php"),
    "go": ("go", "go"),
    "rust": ("rust", "rs"),
    "ruby": ("ruby", "rb"),
    "lua": ("lua", "lua"),
    "bash": ("bash", "sh"),
    "sh": ("bash", "sh"),
    "assembly": ("assembly", "asm"),
    "csharp": ("csharp", "cs"),
    "fsharp": ("fsharp", "fs"),
    "haskell": ("haskell", "hs"),
    "kotlin": ("kotlin", "kt"),
    "perl": ("perl", "pl"),
    "scala": ("scala", "scala"),
    "swift": ("swift", "swift"),
    "typescript": ("typescript", "ts"),
    "clojure": ("clojure", "clj"),
    "coffeescript": ("coffeescript", "coffee"),
    "elixir": ("elixir", "ex"),
    "erlang": ("erlang", "erl"),
    "julia": ("julia", "jl"),
    "nim": ("nim", "nim"),
    "ocaml": ("ocaml", "ml"),
}

async def glot_exec(lang, ext, code):
    url = f"https://glot.io/api/run/{lang}/latest"
    headers = {
        "Authorization": f"Token {GLOT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "files": [{"name": f"main.{ext}", "content": code}]
    }
    async with httpx.AsyncClient() as http:
        response = await http.post(url, json=data, headers=headers)
        return response.json()

async def run_code(client, message):
    cmd = message.command[0]
    lang_info = LANGUAGES.get(cmd)
    
    if not lang_info:
        return
        
    lang, ext = lang_info
    
    code = ""
    if len(message.command) > 1:
        code = message.text.split(None, 1)[1]
    elif message.reply_to_message:
        code = message.reply_to_message.text or message.reply_to_message.caption
        
    if not code:
        return await message.reply_text("Provide code to run.")
        
    # Remove markdown code blocks if present
    code = code.strip().removeprefix("```").removesuffix("```")
    # Also handle language name in code block e.g. ```python ... ```
    if code.startswith(lang):
         code = code[len(lang):].strip()
    elif code.startswith(ext):
         code = code[len(ext):].strip()
         
    msg = await message.reply_text(f"Running {lang} code...")
    
    try:
        result = await glot_exec(lang, ext, code)
        
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        error = result.get("error", "")
        
        output = stdout + stderr + error
        
        if not output:
             output = "No output."
             
        if len(output) > 4096:
             url = await rentry(output)
             await msg.edit(f"**Output too long:** [View on Rentry]({url})", disable_web_page_preview=True)
        else:
             await msg.edit(f"**Output:**\n```\n{output}\n```")
             
    except Exception as e:
        await msg.edit(f"Error: {e}")

    except Exception as e:
        await msg.edit(f"Error: {e}")

from pyrogram.handlers import MessageHandler
app.add_handler(MessageHandler(run_code, filters.command(list(LANGUAGES.keys())) & filters.group))
