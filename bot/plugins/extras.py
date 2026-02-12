import httpx
from pyrogram import filters
from bot import app
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Extras"
__HELP__ = """
<b>Extras:</b>
Useful tools.

/urban <term> - Search Urban Dictionary.
/currency <amount> <from> <to> - Convert currency.
"""

@app.on_message(filters.command(["urban", "ud"]) & filters.group)
@capture_err
async def urban_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /urban <term>")
        
    term = message.text.split(None, 1)[1]
    
    msg = await message.reply_text(f"Searching for <b>{term}</b>...")
    
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"https://api.urbandictionary.com/v0/define?term={term}")
            data = resp.json()
            
        if not data["list"]:
            return await msg.edit("No results found.")
            
        result = data["list"][0]
        definition = result["definition"].replace("[", "").replace("]", "")
        example = result["example"].replace("[", "").replace("]", "")
        author = result["author"]
        
        text = f"<b>Urban Dictionary: {term}</b>\n\n"
        text += f"<b>Definition:</b>\n{definition}\n\n"
        text += f"<b>Example:</b>\n_{example}_\n\n"
        text += f"<b>Author:</b> {author}"
        
        # Truncate if too long
        if len(text) > 4096:
             text = text[:4093] + "..."
             
        await msg.edit(text)
        
    except Exception as e:
        await msg.edit(f"Error: {e}")

@app.on_message(filters.command(["currency", "curr"]) & filters.group)
@capture_err
async def currency_cmd(client, message):
    if len(message.command) < 4:
        return await message.reply_text("Usage: /currency <amount> <from> <to>\nExample: /currency 10 USD IDR")
        
    try:
        amount = float(message.command[1])
        base = message.command[2].upper()
        target = message.command[3].upper()
    except ValueError:
        return await message.reply_text("Invalid amount.")
        
    msg = await message.reply_text("Converting...")
    
    try:
        async with httpx.AsyncClient() as http:
            # Using Free Exchange Rate API
            resp = await http.get(f"https://api.exchangerate-api.com/v4/latest/{base}")
            
            if resp.status_code != 200:
                 return await msg.edit("Invalid currency or API error.")
                 
            data = resp.json()
            rates = data.get("rates", {})
            
            if target not in rates:
                 return await msg.edit(f"Currency {target} not supported.")
                 
            rate = rates[target]
            converted = amount * rate
            
            await msg.edit(f"<b>Currency Converter</b>\n\n{amount} {base} = <b>{converted:,.2f} {target}</b>\nRate: 1 {base} = {rate} {target}")
            
    except Exception as e:
        await msg.edit(f"Error: {e}")
