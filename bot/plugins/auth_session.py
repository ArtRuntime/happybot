from pyrogram import Client, filters, types, enums
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid, PhoneNumberInvalid
from bot import app, db, config, logger, userbot
import asyncio
import os

# Store login states
# {user_id: {"client": Client, "phone": str, "ensure_state": str}}
login_states = {}

@app.on_message(filters.command("login") & filters.private)
async def login_command(_, message: types.Message):
    user_id = message.from_user.id
    
    # Restrict to sudo users only
    if user_id not in app.sudoers:
        await message.reply_text(
            "🔒 **Access Denied**\n\n"
            "This command is restricted to bot administrators only."
        )
        return
    
    if user_id in login_states:
        await message.reply_text("❌ You are already in a login process. Use /stoplogin to stop.")
        return

    text = (
        "🔐 **Assistant Login**\n\n"
        "To Stop the Login flow type /stoplogin\n\n"
        "This will add your account as a music assistant to the bot.\n\n"
        "Please enter your **Phone Number** with country code:\n"
        "Example: `+1234567890`"
    )
    await message.reply_text(text)
    login_states[user_id] = {"state": "wait_phone"}

@app.on_message(filters.command("stoplogin") & filters.private)
async def stop_login(_, message: types.Message):
    user_id = message.from_user.id
    if user_id in login_states:
        client = login_states[user_id].get("client")
        if client:
            try:
                await client.disconnect()
            except:
                pass
        del login_states[user_id]
        await message.reply_text("✅ Login process stopped.")
    else:
        await message.reply_text("ℹ️ No active login process found.")

# Filter to check if user is in login state
async def _is_logging_in(_, __, message):
    return message.from_user and message.from_user.id in login_states

is_logging_in = filters.create(_is_logging_in)

@app.on_message(filters.text & filters.private & is_logging_in)
async def auth_handler(_, message: types.Message):
    user_id = message.from_user.id
    # Filter already checked existence in login_states

    state_data = login_states[user_id]
    step = state_data["state"]

    if step == "wait_phone":
        phone_number = message.text.strip().replace(" ", "")
        
        status_msg = await message.reply_text("🔄 Connecting to Telegram...")
        
        # Initialize User Client with bot's credentials and proxy
        client = Client(
            name=f"login_{user_id}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            in_memory=True,
            proxy=config.PROXY_DICT,
        )
        
        try:
            await client.connect()
        except Exception as e:
            await status_msg.edit_text(f"❌ Failed to connect: {e}")
            del login_states[user_id]
            return

        try:
            sent_code = await client.send_code(phone_number)
            state_data["client"] = client
            state_data["phone"] = phone_number
            state_data["phone_code_hash"] = sent_code.phone_code_hash
            state_data["state"] = "wait_code"
            
            # Determine delivery type for better UX
            delivery_text = "Telegram"
            if sent_code.type == enums.SentCodeType.APP:
                delivery_text = "Telegram App (Service Notifications)"
            elif sent_code.type == enums.SentCodeType.SMS:
                delivery_text = "SMS"
            elif sent_code.type == enums.SentCodeType.CALL:
                delivery_text = "Phone Call"
            elif sent_code.type == enums.SentCodeType.FLASH_CALL:
                delivery_text = "Flash Call"
            
            await status_msg.edit_text(
                f"✅ **Code Sent via {delivery_text}!**\n\n"
                "Please enter the OTP code you received.\n"
                "Format: `1 2 3 4 5` (add spaces between numbers!)"
            )
        except PhoneNumberInvalid:
            await status_msg.edit_text("❌ Invalid phone number. Please try again with /login.")
            await client.disconnect()
            del login_states[user_id]
        except Exception as e:
            await status_msg.edit_text(f"❌ Error sending code: {e}")
            await client.disconnect()
            del login_states[user_id]

    elif step == "wait_code":
        code = message.text.replace(" ", "")
        client = state_data["client"]
        phone_code_hash = state_data["phone_code_hash"]
        phone = state_data["phone"]
        
        status_msg = await message.reply_text("🔄 Verifying code...")

        try:
            await client.sign_in(phone, phone_code_hash, code)
            
            # Login successful
            session_string = await client.export_session_string()
            user_info = await client.get_me()
            name = user_info.first_name
            session_name = f"{name}_{user_id}"
            
            # Save to DB
            try:
                await db.add_session(session_string, session_name, user_id)
                msg_text = f"✅ **Login Successful!**\n\nAssistant `{name}` added to database."
                
                # Start the assistant immediately
                try:
                    await userbot.add_client(session_string, session_name)
                    msg_text += "\n✅ Assistant started successfully!"
                except Exception as ex:
                    msg_text += f"\n⚠️ Failed to auto-start: {ex}"
                
                await status_msg.edit_text(msg_text)

            except ValueError as ve:
                await status_msg.edit_text(f"⚠️ Login successful, but failed to save: {ve}")
            
            await client.disconnect()
            del login_states[user_id]
            
        except SessionPasswordNeeded:
            state_data["state"] = "wait_password"
            await status_msg.edit_text(
                "🔐 **Two-Step Verification Required**\n\n"
                "Please enter your 2FA Password:"
            )
        except PhoneCodeInvalid:
            await status_msg.edit_text("❌ **Invalid Code!**\n\nPlease check the code and send it again.\nUse /stoplogin to cancel.")
        except Exception as e:
            await status_msg.edit_text(f"❌ Error signing in: {e}")
            await client.disconnect()
            del login_states[user_id]

    elif step == "wait_password":
        password = message.text
        client = state_data["client"]
        status_msg = await message.reply_text("🔄 Verifying password...")
        
        try:
            await client.check_password(password=password)
            
            # Login successful
            session_string = await client.export_session_string()
            user_info = await client.get_me()
            name = user_info.first_name
            session_name = f"{name}_{user_id}"
            
            # Save to DB
            try:
                await db.add_session(session_string, session_name, user_id)
                msg_text = f"✅ **Login Successful!**\n\nAssistant `{name}` added to database."
                
                # Start the assistant immediately
                try:
                    await userbot.add_client(session_string, session_name)
                    msg_text += "\n✅ Assistant started successfully!"
                except Exception as ex:
                    msg_text += f"\n⚠️ Failed to auto-start: {ex}"
                
                await status_msg.edit_text(msg_text)
                
            except ValueError as ve:
                await status_msg.edit_text(f"⚠️ Login successful, but failed to save: {ve}")
            
            await client.disconnect()
            del login_states[user_id]
            
        except PasswordHashInvalid:
            await status_msg.edit_text("❌ **Invalid Password!**\n\nPlease check your password and send it again.\nUse /stoplogin to cancel.")
        except Exception as e:
            await status_msg.edit_text(f"❌ Error signing in: {e}")
            await client.disconnect()
            del login_states[user_id]
