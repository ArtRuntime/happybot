# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import filters, types

from bot import anon, app, db, logger, userbot


@app.on_message(filters.command(["addsession"]) & app.sudoers)
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


@app.on_message(filters.command(["rmsession", "removesession"]) & app.sudoers)
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


@app.on_message(filters.command(["sessions", "listsessions"]) & app.sudoers)
async def list_sessions(_, message: types.Message):
    """List all sessions and check their validity."""
    msg = await message.reply_text("⏳ Fetching and validating sessions... This may take a moment.")
    
    try:
        from bot import config
        from pyrogram import Client
        
        sessions = await db.get_all_sessions(include_inactive=True)
        
        if not sessions:
            return await msg.edit_text("📭 No sessions found in database.")
            
        sessions.sort(key=lambda x: x["name"])
        
        text = f"📋 **Session Status Check:**\n\n"
        valid_count = 0
        invalid_count = 0
        
        for idx, session in enumerate(sessions, 1):
            name = session["name"]
            session_string = session["session_string"]
            
            # Check runtime status
            client = userbot._client_map.get(name)
            is_valid = False
            error_reason = ""
            
            if client:
                # Client is online - check if it's still valid
                try:
                    me = await client.get_me()
                    is_valid = True
                    user_id = me.id
                    username = me.username
                except Exception as e:
                    is_valid = False
                    error_reason = str(e)
            else:
                # Client is offline - verify manually
                try:
                    # Create temporary client to check
                    temp_client = Client(
                        name=f"check_{name}",
                        api_id=config.API_ID,
                        api_hash=config.API_HASH,
                        session_string=session_string,
                        in_memory=True,
                        no_updates=True,
                        proxy=config.PROXY_DICT
                    )
                    await temp_client.connect()
                    me = await temp_client.get_me()
                    is_valid = True
                    user_id = me.id
                    username = me.username
                    await temp_client.disconnect()
                except Exception as e:
                    is_valid = False
                    error_reason = str(e)

            # Format Output
            status_icon = "✅" if is_valid else "❌"
            runtime_icon = "🟢" if client else "⚫"
            
            text += f"**{idx}. {name}**\n"
            text += f"   Status: {status_icon} {'Valid' if is_valid else 'Revoked/Invalid'}\n"
            text += f"   State: {runtime_icon} {'Online' if client else 'Offline'}\n"
            
            if is_valid:
                text += f"   ID: `{user_id}`\n"
                if username:
                    text += f"   User: @{username}\n"
                valid_count += 1
            else:
                text += f"   Error: {error_reason[:30]}...\n"
                invalid_count += 1
            
            text += "\n"
            
            # Update status periodically for long lists
            if idx % 5 == 0:
                await msg.edit_text(text + f"\n⏳ Checking {idx}/{len(sessions)}...")
        
        summary = f"\n**Summary:**\nTotal: {len(sessions)} | Valid: {valid_count} | Invalid: {invalid_count}"
        await msg.edit_text(text + summary)
        
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}", exc_info=True)
        await msg.edit_text(f"❌ **Error:** {str(e)}")
