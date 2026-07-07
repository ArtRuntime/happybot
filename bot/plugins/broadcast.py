# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
import asyncio

from pyrogram import enums, errors, filters, types

from bot import app, db, lang


broadcasting = False

@app.on_message(filters.command(["broadcast", "gcast", "brodcast"]) & app.sudoers)
@lang.language()
async def _broadcast(_, message: types.Message):
    global broadcasting
    if not message.reply_to_message:
        return await message.reply_text(message.lang["gcast_usage"])

    if broadcasting:
        return await message.reply_text(message.lang["gcast_active"])

    msg = message.reply_to_message
    count, ucount = 0, 0
    chats, groups, users = [], [], []
    sent = await message.reply_text(message.lang["gcast_start"])

    if "-nochat" not in message.command:
        groups.extend(await db.get_chats())
        if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP] and message.chat.id not in groups:
            await db.add_chat(message.chat.id)
            groups.append(message.chat.id)
            
    if "-user" in message.command or message.chat.type == enums.ChatType.PRIVATE:
        users.extend(await db.get_users())
        if message.chat.type == enums.ChatType.PRIVATE and message.chat.id not in users:
            await db.add_user(message.chat.id)
            users.append(message.chat.id)

    chats.extend(groups + users)
    
    # Check if there are any chats to broadcast to
    if not chats:
        return await message.reply_text("❌ No chats or users found to broadcast to.")

    broadcasting = True
    
    try:
        try:
            await msg.forward(app.logger)
            await (await app.send_message(
                chat_id=app.logger, 
                text=message.lang["gcast_log"].format(
                    message.from_user.id,
                    message.from_user.mention,
                    message.text,
                )
            )).pin(disable_notification=False)
        except Exception as e:
            await message.reply_text(f"⚠️ Warning: Logger access failed: {e}")

        await asyncio.sleep(5)

        failed = ""
        for chat in chats:
            if not broadcasting:
                await sent.edit_text(message.lang["gcast_stopped"].format(count, ucount))
                break

            try:
                # Force Pyrogram to resolve and cache the peer from Telegram's servers
                try:
                    await app.get_chat(chat)
                except Exception:
                    pass

                (
                    await msg.copy(chat, reply_markup=msg.reply_markup)
                    if "-copy" in message.text
                    else await msg.forward(chat)
                )
                if chat in groups:
                    count += 1
                else:
                    ucount += 1
                await asyncio.sleep(0.1)
            except errors.FloodWait as fw:
                await asyncio.sleep(fw.value + 30)
            except (errors.PeerIdInvalid, errors.UserDeactivated, errors.ChatWriteForbidden, errors.ChannelPrivate, errors.UserIsBlocked) as e:
                # Clean up permanently invalid/unreachable chats and users from MongoDB
                if chat in groups:
                    await db.rm_chat(chat)
                else:
                    await db.rm_user(chat)
                failed += f"{chat} - Removed from DB: {e}\n"
            except Exception as ex:
                failed += f"{chat} - {ex}\n"
                continue

        text = message.lang["gcast_end"].format(count, ucount)
        if failed:
            with open("errors.txt", "w") as f:
                f.write(failed)
            await message.reply_document(
                document="errors.txt",
                caption=text,
            )
            os.remove("errors.txt")
        await sent.edit_text(text)
        
    except Exception as e:
        await sent.edit_text(f"❌ Broadcast failed with critical error: {e}")
        
    finally:
        broadcasting = False


@app.on_message(filters.command(["stop_gcast", "stop_broadcast"]) & app.sudoers)
@lang.language()
async def _stop_gcast(_, message: types.Message):
    global broadcasting
    if not broadcasting:
        return await message.reply_text(message.lang["gcast_inactive"])

    broadcasting = False
    await (await app.send_message(
        chat_id=app.logger,
        text=message.lang["gcast_stop_log"].format(
            message.from_user.id,
            message.from_user.mention
        )
    )).pin(disable_notification=False)
    await message.reply_text(message.lang["gcast_stop"])
