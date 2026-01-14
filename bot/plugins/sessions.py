# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types

from bot import anon, app, db, logger, userbot


@app.on_message(filters.command(["addsession"]) & filters.user(app.owner))
async def add_session(_, message: types.Message):
    """
    Add a new assistant session dynamically.
    Usage: /addsession <session_string> [name]
    """
    args = message.text.split(maxsplit=2)
    
    if len(args) < 2:
        return await message.reply_text(
            "**Usage:** `/addsession <session_string> [name]`\n\n"
            "**Example:** `/addsession BQxxx... Assistant 4`\n\n"
            "If name is not provided, it will be auto-generated."
        )
    
    session_string = args[1]
    name = args[2] if len(args) > 2 else f"Assistant {len(userbot.clients) + 1}"
    
    msg = await message.reply_text(f"⏳ Adding session '{name}'...")
    
    try:
        # Add to database
        await db.add_session(session_string, name, message.from_user.id)
        
        # Hot-add to userbot
        client = await userbot.add_client(session_string, name)
        
        # Hot-add PyTgCalls client
        await anon.add_pytgcalls_client(client)
        
        await msg.edit_text(
            f"✅ **Session Added Successfully!**\n\n"
            f"**Name:** `{name}`\n"
            f"**Username:** @{client.username}\n"
            f"**User ID:** `{client.id}`\n\n"
            f"The assistant is now active and ready to handle calls!"
        )
        
    except ValueError as e:
        await msg.edit_text(f"❌ **Error:** {str(e)}")
    except Exception as e:
        logger.error(f"Failed to add session: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ **Failed to add session!**\n\n"
            f"**Error:** `{type(e).__name__}`\n"
            f"**Details:** {str(e)[:200]}"
        )


@app.on_message(filters.command(["rmsession", "removesession"]) & filters.user(app.owner))
async def remove_session(_, message: types.Message):
    """
    Remove an assistant session dynamically.
    Usage: /rmsession <name>
    """
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        return await message.reply_text(
            "**Usage:** `/rmsession <name>`\n\n"
            "**Example:** `/rmsession Assistant 1`"
        )
    
    name = args[1]
    msg = await message.reply_text(f"⏳ Removing session '{name}'...")
    
    try:
        # Get the client before removing (optional check)
        client = userbot._client_map.get(name)
        
        # Try to remove from runtime, but don't stop if it fails
        if client:
            try:
                await anon.remove_pytgcalls_client(client)
            except Exception as e:
                logger.error(f"Failed to remove PyTgCalls client: {e}")
            
            try:
                await userbot.remove_client(name)
            except Exception as e:
                logger.error(f"Failed to remove Userbot client: {e}")
        
        # Always attempt to remove from database
        removed = await db.remove_session(name)
        
        if removed:
            await msg.edit_text(
                f"✅ **Session Removed Successfully!**\n\n"
                f"**Name:** `{name}`\n\n"
                f"The assistant has been removed from the database."
            )
        else:
            await msg.edit_text(f"⚠️ Session '{name}' not found in database, but runtime cleanup was attempted.")
            
    except Exception as e:
        logger.error(f"Failed to remove session: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ **Failed to remove session!**\n\n"
            f"**Error:** `{type(e).__name__}`\n"
            f"**Details:** {str(e)[:200]}"
        )


@app.on_message(filters.command(["sessions", "listsessions"]) & filters.user(app.owner))
async def list_sessions(_, message: types.Message):
    """List all active sessions."""
    msg = await message.reply_text("⏳ Fetching sessions...")
    
    try:
        sessions = await db.get_sessions()
        
        if not sessions:
            return await msg.edit_text("📭 No active sessions found.")
        
        text = f"📋 **Active Sessions ({len(sessions)}):**\n\n"
        
        for idx, session in enumerate(sessions, 1):
            client = userbot._client_map.get(session["name"])
            status = "🟢 Online" if client else "🔴 Offline"
            
            text += f"**{idx}.**\n`{session['name']}`\n"
            text += f"   • Status: {status}\n"
            
            if client:
                text += f"   • Username: @{client.username}\n"
                text += f"   • User ID: `{client.id}`\n"
            
            text += f"   • Added by: `{session['added_by']}`\n"
            text += f"   • Added at: {session['added_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
        
        await msg.edit_text(text)
        
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}", exc_info=True)
        await msg.edit_text(f"❌ **Error:** {str(e)}")
