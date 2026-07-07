import asyncio
import uuid
from pyrogram import filters, Client
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.errors import FloodWait, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import app, config, db, logger
from bot.helpers.feds_utils import (
    capture_err,
    extract_user,
    extract_user_and_reason,
    int_to_alpha,
)

__MODULE__ = "Federation"
__HELP__ = """
<b>Federation Commands:</b>

/newfed <fedname> - Create a new Federation.
/delfed <fedid> - Delete a Federation.
/renamefed <fedid> <newname> - Rename a Federation.
/joinfed <fedid> - Join a Federation (Group Owner Only).
/leavefed <fedid> - Leave a Federation.
/fban <user> <reason> - Ban a user globally in the federation.
/unfban <user> <reason> - Unban a user globally.
/fedinfo <fedid> - Get info about a Federation.
/fedadmins <fedid> - List Federation Admins.
/fpromote <user> - Promote a user to Federation Admin.
/fdemote <user> - Demote a Federation Admin.
/fedchats <fedid> - List chats in a Federation.
/chatfed - Check which Federation the current chat is in.
/myfeds - List Federations you own.
/setfedlog <fedid> - Set the current chat as the Federation Log channel.
/unsetfedlog <fedid> - Unset the Federation Log channel.
/fedstat <user> <fedid> - Check if a user is banned in a Federation.
"""

SUPPORT_CHAT = config.SUPPORT_CHAT

@app.on_message(filters.command("newfed"))
@capture_err
async def new_fed(client, message):
    chat = message.chat
    user = message.from_user
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text(
            "Federations can only be created by privately messaging me."
        )
    if len(message.command) < 2:
        return await message.reply_text("Please write the name of the federation!")
    fednam = message.text.split(None, 1)[1]
    if fednam != "":
        fed_id = str(uuid.uuid4())
        fed_name = fednam
        
        x = await db.create_fed(fed_id=fed_id, fed_name=fed_name, user_id=user.id)
        
        if not x:
            return await message.reply_text(
                f"Can't federate! Please contact {SUPPORT_CHAT} if the problem persist."
            )

        await message.reply_text(
            f"<b>You have succeeded in creating a new federation!</b>\nName: <code>{fed_name}</code>\nID: <code>{fed_id}</code>\n\nUse the command below to join the federation:\n<code>/joinfed {fed_id}</code>",
            parse_mode=ParseMode.MARKDOWN,
        )
        try:
            if config.LOGGER_ID:
                await app.send_message(
                    config.LOGGER_ID,
                    f"New Federation: <b>{fed_name}</b>\nID: <pre>{fed_id}</pre>",
                    parse_mode=ParseMode.HTML,
                )
        except:
            pass
    else:
        await message.reply_text("Please write down the name of the federation")


@app.on_message(filters.command("delfed"))
@capture_err
async def del_fed(client, message):
    chat = message.chat
    user = message.from_user
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text(
            "Federations can only be deleted by privately messaging me."
        )
    args = message.text.split(" ", 1)
    if len(args) <= 1:
        return await message.reply_text("What should I delete?")
    is_fed_id = args[1].strip()
    getinfo = await db.get_fed_info(is_fed_id)
    if not getinfo:
        return await message.reply_text("This federation does not exist.")
    
    sudoers = await db.get_sudoers()
    if getinfo["owner_id"] == user.id or user.id in sudoers or user.id == config.OWNER_ID:
        fed_id = is_fed_id
    else:
        return await message.reply_text("Only federation owners can do this!")
    
    await message.reply_text(
        f"""You sure you want to delete your federation? This cannot be reverted, you will lose your entire ban list, and '{getinfo["fed_name"]}' will be permanently lost.""",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⚠️ Delete Federation ⚠️",
                        callback_data=f"rmfed_{fed_id}",
                    )
                ],
                [InlineKeyboardButton("Cancel", callback_data="rmfed_cancel")],
            ]
        ),
    )


@app.on_callback_query(filters.regex("rmfed_(.*)"))
async def del_fed_btn(client, cb):
    query = cb.data
    if query == "rmfed_cancel":
        await cb.message.edit("Federation deletion cancelled.")
        return

    fed_id = query.split("_")[1]
    user = cb.from_user
    getinfo = await db.get_fed_info(fed_id)
    
    if not getinfo:
        await cb.message.edit("This federation does not exist.")
        return
        
    sudoers = await db.get_sudoers()
    if getinfo["owner_id"] == user.id or user.id in sudoers or user.id == config.OWNER_ID:
        await db.del_fed(fed_id)
        await cb.message.edit(f"Federation <b>{getinfo['fed_name']}</b> has been deleted.")
    else:
        await cb.answer("Only federation owners can do this!", show_alert=True)


@app.on_message(filters.command("myfeds"))
@capture_err
async def myfeds(client, message):
    if not message.from_user:
        return
    user = message.from_user
    is_feds = await db.get_feds_by_owner(int(user.id))

    if is_feds:
        response_text = "\n\n".join(
            [
                f"{i + 1}.\n<b>Fed Name:</b> {fed['fed_name']}\n<b>Fed Id:</b> <code>{fed['fed_id']}</code>"
                for i, fed in enumerate(is_feds)
            ]
        )
        await message.reply_text(
            f"<b>Here are the federations you have created:</b>\n\n{response_text}"
        )
    else:
        await message.reply_text("<b>You haven't created any federations.</b>")


@app.on_message(filters.command("renamefed"))
@capture_err
async def rename_fed(client, message):
    if not message.from_user:
        return
    user = message.from_user
    msg = message
    args = msg.text.split(None, 2)

    if len(args) < 3:
        return await msg.reply_text("usage: /renamefed <fed_id> <newname>")

    fed_id, newname = args[1], args[2]
    verify_fed = await db.get_fed_info(fed_id)

    if not verify_fed:
        return await msg.reply_text("This fed does not exist in my database!")

    if verify_fed["owner_id"] == user.id:
        await db.fed_rename(fed_id, newname)
        await msg.reply_text(f"Successfully renamed your fed name to {newname}!")
    else:
        await msg.reply_text("Only federation owner can do this!")


@app.on_message(filters.command(["setfedlog", "unsetfedlog"]))
@capture_err
async def fed_log(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "Send this command on the chat which you need to set as fed log channel."
        )
    member = await app.get_chat_member(chat.id, user.id)
    if member.status in [
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
    ]:
        if len(message.command) < 2:
            return await message.reply_text(
                "Please provide the Id of the federation with the command!"
            )
        fed_id = message.text.split(" ", 1)[1].strip()
        info = await db.get_fed_info(fed_id)
        if not info:
            return await message.reply_text("This federation does not exist.")
        
        if info["owner_id"] == user.id:
            # For now, simplistic log setting (storing in mongo not fully implemented in create_fed but logic is here)
            # To support logging properly, we need to update the fed doc
             await db.db.feds.update_one(
                {"fed_id": str(fed_id)},
                {"$set": {"log_group_id": chat.id if "/setfedlog" in message.text else None}}
             )
             
             if "/unsetfedlog" in message.text:
                return await message.reply_text("log channel removed successfully.")
             else:
                await message.reply_text("log channel set successfully.")
        else:
            await message.reply_text("Only federation owner can do this!")
    else:
        await message.reply_text(
            "You need to be the chat owner or admin to use this command."
        )


@app.on_message(filters.command("chatfed"))
@capture_err
async def fed_chat(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user
    fed_id = await db.get_fed_id(chat.id)

    try:
        member = await client.get_chat_member(chat.id, user.id)
        if member.status not in [
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
        ]:
             # Allow checking if regular user? MissKaty says must be admin
             return await message.reply_text("You must be an admin to execute this command")
    except:
        pass

    if not fed_id:
        return await message.reply_text("This group is not in any federation!")
    info = await db.get_fed_info(fed_id)

    text = f'This group is part of the following federation:\n{info["fed_name"]} (ID: <code>{fed_id}</code>)'
    await message.reply_text(text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command("joinfed"))
@capture_err
async def join_fed(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is specific to groups, not our pm!",
        )

    member = await client.get_chat_member(chat.id, user.id)
    fed_id = await db.get_fed_id(int(chat.id))

    sudoers = await db.get_sudoers()
    if (
        user.id in sudoers or user.id == config.OWNER_ID or member.status != ChatMemberStatus.OWNER
    ) and user.id not in sudoers and user.id != config.OWNER_ID:
        return await message.reply_text("Only group creators can use this command!")
    
    if fed_id:
        return await message.reply_text("You cannot join two federations from one chat")
    
    args = message.text.split(" ", 1)
    if len(args) > 1:
        fed_id = args[1].strip()
        getfed = await db.search_fed_by_id(fed_id)
        if not getfed:
            return await message.reply_text("Please enter a valid federation ID")

        await db.chat_join_fed(fed_id, chat.title, chat.id)
        
        if get_fedlog := getfed.get("log_group_id"):
            try:
                await app.send_message(
                    get_fedlog,
                    f'Chat <b>{chat.title}</b> has joined the federation <b>{getfed["fed_name"]}</b>',
                    parse_mode=ParseMode.MARKDOWN,
                )
            except:
                pass

        await message.reply_text(
            f'This group has joined the federation: {getfed["fed_name"]}!'
        )
    else:
        await message.reply_text(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )


@app.on_message(filters.command("leavefed"))
@capture_err
async def leave_fed(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user

    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is specific to groups, not our pm!",
        )

    fed_id = await db.get_fed_id(int(chat.id))
    if not fed_id:
        return await message.reply_text("This chat is not in any federation!")
        
    fed_info = await db.get_fed_info(fed_id)

    member = await app.get_chat_member(chat.id, user.id)
    sudoers = await db.get_sudoers()
    
    if member.status == ChatMemberStatus.OWNER or user.id in sudoers or user.id == config.OWNER_ID:
        if await db.chat_leave_fed(int(chat.id)):
            if get_fedlog := fed_info.get("log_group_id"):
                try:
                    await app.send_message(
                        get_fedlog,
                        f'Chat <b>{chat.title}</b> has left the federation <b>{fed_info["fed_name"]}</b>',
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except:
                    pass
            await message.reply_text(
                f'This group has left the federation {fed_info["fed_name"]}!'
            )
        else:
            await message.reply_text(
                "How can you leave a federation that you never joined?!"
            )
    else:
        await message.reply_text("Only group creators can use this command!")


@app.on_message(filters.command("fedchats"))
@capture_err
async def fed_chats_list(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text(
            "Fedchats can only be checked by privately messaging me."
        )
    if len(message.command) < 2:
        return await message.reply_text(
            "Please write the Id of the federation!\n\nUsage:\n/fedchats fed_id"
        )
    args = message.text.split(" ", 1)
    if len(args) > 1:
        fed_id = args[1].strip()
        info = await db.get_fed_info(fed_id)
        if not info:
            return await message.reply_text("This federation does not exist.")
        fed_owner = info["owner_id"]
        fed_admins = info["fadmins"]
        
        sudoers = await db.get_sudoers()
        all_admins = [fed_owner] + fed_admins + [client.me.id]
        
        if user.id not in all_admins and user.id not in sudoers and user.id != config.OWNER_ID:
            return await message.reply_text(
                "You need to be a Fed Admin to use this command"
            )

        chat_ids = info.get("chat_ids", [])
        if not chat_ids:
            return await message.reply_text("There are no chats in this federation!")
        
        # MissKatyPyro stored names, but we only stored IDs in my mongo implementation? 
        # Wait, mongo.py <code>chat_join_fed</code> only adds <code>chat_id</code>. 
        # I should fetch names? Or just list IDs. 
        # MissKatyPyro used a separate helper <code>chat_id_and_names_in_fed</code>.
        # I'll just list IDs for now, or fetch titles if possible (slow).
        text = "\n".join(
            [
                f"[<code>{chat_id}</code>]"
                for chat_id in chat_ids
            ]
        )
        await message.reply_text(
            f"<b>Here are the list of chats connected to this federation:</b>\n\n{text}"
        )


@app.on_message(filters.command("fedinfo"))
@capture_err
async def fed_info_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Please provide the Fed Id to get information!")

    fed_id = message.text.split(" ", 1)[1].strip()
    fed_info = await db.get_fed_info(fed_id)

    if not fed_info:
        return await message.reply_text("Federation not found.")

    fed_name = fed_info.get("fed_name")
    
    # Resolving owner mention
    try:
        owner = await app.get_users(fed_info.get("owner_id"))
        owner_mention = owner.mention
    except:
        owner_mention = str(fed_info.get("owner_id"))
        
    fadmin_count = len(fed_info.get("fadmins", []))
    banned_users_count = len(fed_info.get("banned_users", []))
    chat_ids_count = len(fed_info.get("chat_ids", []))

    reply_text = (
        f"<b>Federation Information:</b>\n\n"
        f"<b>Fed Name:</b> {fed_name}\n"
        f"<b>Owner:</b> {owner_mention}\n"
        f"<b>Number of Fed Admins:</b> {fadmin_count}\n"
        f"<b>Number of Banned Users:</b> {banned_users_count}\n"
        f"<b>Number of Chats:</b> {chat_ids_count}"
    )

    await message.reply_text(reply_text)


@app.on_message(filters.command("fedadmins"))
@capture_err
async def get_all_fadmins_mentions(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Please provide me the Fed Id to search!")

    fed_id = message.text.split(" ", 1)[1].strip()
    fed_info = await db.get_fed_info(fed_id)
    if not fed_info:
        return await message.reply_text("Federation not found.")

    fadmin_ids = fed_info.get("fadmins", [])
    
    try:
        owner = await app.get_users(fed_info.get("owner_id"))
        owner_mention = owner.mention
    except:
        owner_mention = str(fed_info.get("owner_id"))

    if not fadmin_ids:
        return await message.reply_text(
            f"**Owner: {owner_mention}\n\nNo fadmins found in the federation."
        )

    user_mentions = []
    for user_id in fadmin_ids:
        try:
            user = await app.get_users(int(user_id))
            user_mentions.append(f"● {user.mention}[<code>{user.id}</code>]")
        except Exception:
            user_mentions.append(f"● <code>Admin🥷</code>[<code>{user_id}</code>]")
    reply_text = (
        f"<b>Owner: {owner_mention}\n\nList of fadmins:</b>\n"
        + "\n".join(user_mentions)
    )
    await message.reply_text(reply_text)


@app.on_message(filters.command("fpromote"))
@capture_err
async def fpromote(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user
    msg = message

    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is specific to groups, not our pm! (for security)",
        )

    fed_id = await db.get_fed_id(chat.id)
    if not fed_id:
        return await message.reply_text(
            "You need to add a federation to this chat first!"
        )

    verify_fed = await db.get_fed_info(fed_id)
    sudoers = await db.get_sudoers()
    
    if verify_fed["owner_id"] == user.id or user.id in sudoers or user.id == config.OWNER_ID:
        user_id = await extract_user(msg)

        if user_id is None:
            return await message.reply_text("Failed to extract user from the message.")
            
        check_user = await db.check_banned_user(fed_id, user_id)
        if check_user:
            return await message.reply_text(
                f"<b>User is Fed Banned. Unban them first.</b>"
            )

        if user_id == verify_fed["owner_id"]:
            return await message.reply_text(
                "You do know that the user is the federation owner, right?"
            )

        if await db.search_user_in_fed(fed_id, user_id):
            return await message.reply_text(
                "User is already a federation admin."
            )

        if user_id == client.me.id:
            return await message.reply_text(
                "I am already a federation admin in all federations!"
            )
            
        res = await db.user_join_fed(str(fed_id), user_id)
        if res:
            await message.reply_text("Successfully Promoted!")
        else:
            await message.reply_text("Failed to promote!")
    else:
        await message.reply_text("Only federation owners can do this!")


@app.on_message(filters.command("fdemote"))
@capture_err
async def fdemote(client, message):
    if not message.from_user:
        return
    chat = message.chat
    user = message.from_user
    msg = message

    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is specific to groups.",
        )

    fed_id = await db.get_fed_id(chat.id)
    if not fed_id:
        return await message.reply_text(
            "You need to add a federation to this chat first!"
        )
        
    verify_fed = await db.get_fed_info(fed_id)
    sudoers = await db.get_sudoers()

    if verify_fed["owner_id"] == user.id or user.id in sudoers or user.id == config.OWNER_ID:
        user_id = await extract_user(msg)

        if user_id is None:
            return await message.reply_text("Failed to extract user from the message.")

        if user_id == client.me.id:
            return await message.reply_text(
                "You cannot demote me."
            )

        if not await db.search_user_in_fed(fed_id, user_id):
            return await message.reply_text(
                "I cannot demote people who are not federation admins!"
            )

        res = await db.user_demote_fed(fed_id, user_id)
        await message.reply_text("Demoted from a Fed Admin!")
    else:
        await message.reply_text("Only federation owners can do this!")


@app.on_message(filters.command(["fban", "sfban"]))
@capture_err
async def fban_user(client, message):
    if not message.from_user:
        return
    chat = message.chat
    from_user = message.from_user
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is specific to groups, not our pm!."
        )
    fed_id = await db.get_fed_id(chat.id)
    if not fed_id:
        return await message.reply_text("<b>This chat is not a part of any federation.</b>")
        
    info = await db.get_fed_info(fed_id)
    fed_admins = info.get("fadmins", [])
    fed_owner = info["owner_id"]
    
    sudoers = await db.get_sudoers()
    all_admins = [fed_owner] + fed_admins + [client.me.id]
    
    if from_user.id not in all_admins and from_user.id not in sudoers and from_user.id != config.OWNER_ID:
        return await message.reply_text(
            "You need to be a Fed Admin to use this command"
        )
        
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>You needed to specify a user or reply to their message!</b>"
        )
        
    user_id, reason = await extract_user_and_reason(message)
    
    if not user_id:
        return await message.reply_text("I can't find that user.")
        
    try:
        user = await app.get_users(user_id)
    except PeerIdInvalid:
        user = None
        
    if user_id in all_admins or user_id in sudoers or user_id == config.OWNER_ID:
        return await message.reply_text("I can't ban that user.")
        
    check_user = await db.check_banned_user(fed_id, user_id)
    if check_user:
        reason = check_user["reason"]
        date = check_user["date"]
        return await message.reply_text(
            f"<b>User {user.mention if user else user_id} was already Fed Banned.\n\nReason: {reason}.\nDate: {date}.</b>"
        )
        
    if not reason:
        reason = "No Reason Provided"

    served_chats = info.get("chat_ids", [])
    m = await message.reply_text(
        f"<b>Fed Banning {user.mention if user else user_id}!</b>"
        + f" <b>This Action Should Take About {len(served_chats)} Seconds.</b>"
    )
    
    await db.add_fban_user(fed_id, user_id, reason)
    
    number_of_chats = 0
    # Background this to avoid blocking?
    # For now, simplistic loop (MissKaty does simple loop with sleeps)
    for served_chat in served_chats:
        try:
           # Check if user is in chat to avoid random API hits? 
           # MissKaty checks get_chat_member first.
           try:
               chat_member = await app.get_chat_member(int(served_chat), int(user_id))
               if chat_member.status == ChatMemberStatus.MEMBER:
                   await app.ban_chat_member(int(served_chat), int(user_id))
                   if int(served_chat) != chat.id:
                       if not message.text.startswith("/s"):
                           await app.send_message(
                               int(served_chat), f"<b>Fed Banned {user.mention if user else user_id} !</b>"
                           )
                   number_of_chats += 1
           except:
               pass
               
           await asyncio.sleep(0.5)
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
            
    await m.edit(f"Fed Banned {user.mention if user else user_id} !")
    
    ban_text = f"<b>New Federation Ban</b>\n<b>Origin:</b> {message.chat.title} [<code>{message.chat.id}</code>]\n<b>Admin:</b> {from_user.mention}\n<b>Banned User:</b> {user.mention if user else user_id}\n<b>Reason:</b> {reason}\n<b>Chats:</b> <code>{number_of_chats}</code>"
    
    if info.get("log_group_id"):
        try:
            await app.send_message(
                info["log_group_id"],
                text=ban_text
            )
        except:
            pass


@app.on_message(filters.command(["unfban", "sunfban"]))
@capture_err
async def funban_user(client, message):
    if not message.from_user:
        return
    chat = message.chat
    from_user = message.from_user
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is specific to groups, not our pm!."
        )
    fed_id = await db.get_fed_id(chat.id)
    if not fed_id:
        return await message.reply_text("<b>This chat is not a part of any federation.</b>")
        
    info = await db.get_fed_info(fed_id)
    fed_admins = info.get("fadmins", [])
    fed_owner = info["owner_id"]
    
    sudoers = await db.get_sudoers()
    all_admins = [fed_owner] + fed_admins + [client.me.id]
    
    if from_user.id not in all_admins and from_user.id not in sudoers and from_user.id != config.OWNER_ID:
        return await message.reply_text(
            "You need to be a Fed Admin to use this command"
        )
        
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>You needed to specify a user or reply to their message!</b>"
        )
        
    user_id, reason = await extract_user_and_reason(message)
    if not user_id:
        return await message.reply_text("I can't find that user.")
        
    try:
        user = await app.get_users(user_id)
    except:
        user = None

    check_user = await db.check_banned_user(fed_id, user_id)
    if not check_user:
        return await message.reply_text(
            "<b>I can't unban a user who was never fedbanned.</b>"
        )

    served_chats = info.get("chat_ids", [])
    m = await message.reply_text(
        f"<b>Fed UnBanning {user.mention if user else user_id}!</b>"
        + f" <b>This Action Should Take About {len(served_chats)} Seconds.</b>"
    )
    
    await db.remove_fban_user(fed_id, user_id)
    
    number_of_chats = 0
    for served_chat in served_chats:
        try:
            # Try to unban in all chats
            try:
                await app.unban_chat_member(int(served_chat), int(user_id))
                number_of_chats += 1
            except:
                pass
            await asyncio.sleep(0.5)
        except:
            pass
            
    await m.edit(f"Fed UnBanned {user.mention if user else user_id} !")
