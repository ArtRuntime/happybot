# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

"""
Voice Chat Join/Leave Logger
Logs when members are invited to voice chat during music playback.
"""

# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

"""
Voice Chat Join/Leave Logger
Logs participant join/leave events in groups where music is playing.
"""

import asyncio
from datetime import datetime
from pyrogram import Client, errors, filters
from pyrogram.raw import functions

from bot import app, db, logger, userbot

# Cache: {chat_id: {user_id_1, user_id_2, ...}}
_participants_cache = {}

# Lock to prevent concurrent polling for same chat
_polling_locks = {}

async def get_vc_participants(chat_id: int):
    """Fetch current VC participants using userbot."""
    try:
        # Use the assistant assigned to this chat
        ub = await db.get_client(chat_id)
        if not ub:
            # Fallback to first client if assignment fails
            ub = userbot.clients[0]
        
        # Get chat info to find group call
        chat = await ub.get_chat(chat_id)
        # logger.info(f"VC Debug: Chat type: {chat.type}, Linked: {chat.linked_chat}")
        
        if not chat.linked_chat:
            # If no linked chat (channel), use the group itself
            peer = await ub.resolve_peer(chat_id)
        else:
            # If linked to a channel, we might need to check there
            # For supergroups with linked channels, the call is often on the group
            peer = await ub.resolve_peer(chat_id)

        # Get full chat info to find generic group call
        # InputPeerChannel has channel_id, not chat_id
        if hasattr(peer, 'channel_id'):
            full_chat = await ub.invoke(functions.channels.GetFullChannel(channel=peer))
        else:
            full_chat = await ub.invoke(functions.messages.GetFullChat(chat_id=peer.chat_id))
        
        if not full_chat.full_chat.call:
            logger.warning(f"VC Debug: No call found in full_chat for {chat_id}")
            return set()
            
        call = full_chat.full_chat.call
        # logger.info(f"VC Debug: Found call object: {call}")

        # Fetch participants
        participants = set()
        
        results = await ub.invoke(
            functions.phone.GetGroupParticipants(
                call=call,
                ids=[],
                sources=[],
                offset="",
                limit=100
            )
        )
        
        # logger.info(f"VC Debug: fetched {len(results.participants)} raw participants")
        
        for p in results.participants:
            participants.add(p.peer.user_id)
            
        return participants
        
    except Exception as e:
        from pyrogram.errors import AuthKeyUnregistered, ChannelInvalid
        if isinstance(e, AuthKeyUnregistered) or "401 AUTH_KEY_UNREGISTERED" in str(e):
            logger.error(f"VC Logger detected unregistered client: {e}")
            if 'ub' in locals() and hasattr(ub, 'name'):
                await db.remove_session(ub.name)
                await userbot.remove_client(ub.name)
        elif isinstance(e, ChannelInvalid) or "CHANNEL_INVALID" in str(e):
            logger.warning(f"VC Logger: Chat/Channel {chat_id} is invalid or inaccessible to the assistant.")
        else:
            logger.error(f"Failed to fetch VC participants for {chat_id}: {e}")
        return set()


async def vc_poll_worker():
    """Periodic task to poll VC participants."""
    while True:
        await asyncio.sleep(5)  # Poll every 5 seconds
        
        # Only check chats with active playback
        active_chats = list(db.active_calls.keys())
        if not active_chats:
            continue
            
        for chat_id in active_chats:
            try:
                # Check if Logger is enabled for this chat
                if not await db.get_vc_logger_enabled(chat_id):
                    # Clear cache if disabled to reset state if re-enabled
                    if chat_id in _participants_cache:
                        del _participants_cache[chat_id]
                    continue

                # Initialize cache if not exists
                if chat_id not in _participants_cache:
                    _participants_cache[chat_id] = await get_vc_participants(chat_id)
                    continue
                
                # Fetch current participants
                current_users = await get_vc_participants(chat_id)
                
                # Compare with cached
                cached_users = _participants_cache[chat_id]
                
                # Find joined users
                joined = current_users - cached_users
                
                for user_id in joined:
                    try:
                        user = await app.get_users(user_id)
                        if user.is_bot:
                            continue
                        user_name = user.mention or user.first_name
                        try:
                            await app.send_message(
                                chat_id,
                                f"{user_name} joined voice chat",
                                disable_notification=True
                            )
                        except Exception as e:
                            logger.error(f"VC Logger: Failed to send join msg: {e}")
                    except Exception as e:
                        logger.error(f"VC Logger: Failed to get user {user_id}: {e}")
                
                # Find left users
                left = cached_users - current_users

                for user_id in left:
                    try:
                        user = await app.get_users(user_id)
                        if user.is_bot:
                            continue
                        user_name = user.mention or user.first_name
                        try:
                            await app.send_message(
                                chat_id,
                                f"{user_name} left voice chat",
                                disable_notification=True
                            )
                        except Exception as e:
                            logger.error(f"VC Logger: Failed to send leave msg: {e}")
                    except Exception as e:
                        logger.error(f"VC Logger: Failed to get user {user_id}: {e}")
                
                # Update cache
                _participants_cache[chat_id] = current_users
                
            except Exception as e:
                logger.error(f"Error in VC poll for {chat_id}: {e}")


# Start the polling worker when the bot starts
asyncio.create_task(vc_poll_worker())


@app.on_message(filters.command("vclogger") & filters.group)
async def vclogger_command(client, message):
    """
    Enable/Disable Voice Chat Logger for this chat.
    Usage: /vclogger [on/off]
    """
    if not message.from_user:
        return
        
    chat_id = message.chat.id
    
    # Check permissions (Admin or Sudo)
    if not await db.get_admins(chat_id):
        return
        
    user_id = message.from_user.id
    admins = await db.get_admins(chat_id)
    sudoers = await db.get_sudoers()
    
    if user_id not in admins and user_id not in sudoers:
        return await message.reply_text("❌ You don't have permission to use this command.")
        
    if len(message.command) != 2:
        # Show current status
        status = await db.get_vc_logger_enabled(chat_id)
        state_text = "Enabled ✅" if status else "Disabled ❌"
        return await message.reply_text(
            f"**Voice Chat Logger**\n\n"
            f"Current Status: {state_text}\n"
            f"Usage: `/vclogger on` or `/vclogger off`"
        )
        
    state = message.command[1].lower()
    if state == "on":
        await db.set_vc_logger_enabled(chat_id, True)
        await message.reply_text("✅ Voice Chat Logger **Enabled** for this chat.")
    elif state == "off":
        await db.set_vc_logger_enabled(chat_id, False)
        await message.reply_text("❌ Voice Chat Logger **Disabled** for this chat.")
    else:
        await message.reply_text("Usage: `/vclogger on` or `/vclogger off`")
