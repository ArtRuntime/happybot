# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import asyncio
from pyrogram import Client

from bot import config, logger


class Userbot(Client):
    def __init__(self):
        """
        Initializes the userbot with dynamic session loading from MongoDB.
        Uses Lazy Loading to handle infinite assistants efficiently.
        """
        self.clients = [] # Keep list for back-compat if needed, but mostly rely on map
        self._client_map = {}  # Maps session name to client instance
        self._starting_locks = {} # Lock for concurrent start requests

    async def _create_client(self, session_string: str, name: str) -> Client:
        """Create a new Pyrogram client from session string."""
        client = Client(
            name=f"bot_{name}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=session_string,
            proxy=config.PROXY_DICT,
            no_updates=True, # We don't need updates for assistants usually
        )
        return client

    async def add_client(self, session_string: str, name: str) -> Client:
        """
        Dynamically add and start a new client (hot-reload).
        """
        if name in self._client_map:
            return self._client_map[name]
        
        client = await self._create_client(session_string, name)
        try:
            await client.start()
            me = await client.get_me()
        except Exception as e:
            from pyrogram.errors import AuthKeyUnregistered
            if isinstance(e, AuthKeyUnregistered) or "401 AUTH_KEY_UNREGISTERED" in str(e):
                from bot import db
                logger.error(f"Session '{name}' is unregistered/logged out. Removing it from database.")
                await db.remove_session(name)
                raise ValueError(f"Session '{name}' is unregistered (401 AuthKeyUnregistered)")
            raise
        
        client.id = me.id
        client.name = name  # Use our internal name
        client.user_name = me.first_name # Telegram name
        client.username = me.username
        client.mention = me.mention
        
        self.clients.append(client)
        self._client_map[name] = client
        
        try:
            await client.join_chat("FallenAssociation")
        except:
            pass
        
        # Register with PyTgCalls
        from bot import anon
        await anon.add_pytgcalls_client(client)
        
        logger.info(f"Assistant '{name}' started as @{client.username}")
        
        # Auto-setup log group if main bot is active
        from bot import app
        if app.is_connected:
            asyncio.create_task(self._setup_log_group(client))
            
        return client

    async def get_client_by_name(self, name: str) -> Client:
        """
        Get an assistant client by name.
        If it's not running, fetch from DB and start it (Lazy Load).
        """
        if name in self._client_map:
            return self._client_map[name]
            
        import asyncio
        from bot import db
        
        # Use a lock to prevent race conditions if multiple tasks request same inactive assistant
        if name not in self._starting_locks:
            self._starting_locks[name] = asyncio.Lock()
            
        async with self._starting_locks[name]:
            # Double check after acquiring lock
            if name in self._client_map:
                return self._client_map[name]
                
            logger.info(f"Lazy loading assistant '{name}'...")
            session_doc = await db.get_session_by_name(name)
            if not session_doc:
                raise ValueError(f"Session '{name}' not found in database")
                
            client = await self.add_client(
                session_doc["session_string"],
                session_doc["name"]
            )
            return client

    async def remove_client(self, name: str) -> bool:
        """
        Dynamically remove a client (hot-reload).
        """
        if name not in self._client_map:
            return False
        
        client = self._client_map[name]
        
        # Stop PyTgCalls client first
        from bot import anon
        await anon.remove_pytgcalls_client(client)
        
        # Stop the client
        try:
            await client.stop()
        except:
            pass
        
        # Remove from lists
        if client in self.clients:
            self.clients.remove(client)
        del self._client_map[name]
        
        logger.info(f"Assistant '{name}' stopped and removed")
        return True

    async def boot(self):
        """
        Pre-load assistants and initialize.
        Note: We NO LONGER start all sessions here. They are lazy loaded.
        """
        from bot import db
        
        # Always start the first 3 assistants for readiness
        logger.info("Pre-loading top 3 assistants...")
        try:
            all_sessions = await db.get_all_sessions(include_inactive=False)
            # Sort by name to ensure consistent "Assistant 1/2/3" loading
            all_sessions.sort(key=lambda x: x["name"])
            
            count = 0
            for session in all_sessions:
                if count >= 3:
                    break
                try:
                    await self.add_client(session["session_string"], session["name"])
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to pre-load assistant {session['name']}: {e}")
                    
            logger.info(f"Pre-loaded {count} assistants.")
        except Exception as e:
            logger.error(f"Failed to pre-load assistants: {e}")
            
        logger.info("Userbot Manager initialized (Lazy Loading Enabled)")

    async def _setup_log_group(self, client: Client):
        """Helper to invite assistant to logs group and send startup message."""
        if not config.LOGGER_ID or config.LOGGER_ID > 0:
            return
            
        # Avoid duplicate setup/messages
        if getattr(client, "log_setup_done", False):
            return
            
        from bot import app
        from pyrogram import types, enums
        
        logger.info(f"Setting up logs group for '{client.name}'...")
        
        # Pre-resolve assistant peer on main bot to avoid PEER_ID_INVALID
        try:
            if getattr(client, "username", None):
                await app.get_users(client.username)
            else:
                await app.get_users(client.id)
        except Exception as e:
            logger.debug(f"Failed to pre-resolve peer for '{client.name}': {e}")

        # Check if assistant is already in the logs group (via self-check to avoid PEER_ID_INVALID)
        is_member = False
        is_admin = False
        try:
            member = await client.get_chat_member(config.LOGGER_ID, "me")
            is_member = True
            # Check if already an admin
            if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                is_admin = True
                logger.debug(f"✓ Assistant '{client.name}' already in logs group (admin)")
            else:
                logger.debug(f"✓ Assistant '{client.name}' already in logs group (member)")
        except Exception as e:
            logger.debug(f"✗ Assistant '{client.name}' not in logs group yet (via self-check): {e}")
        
        # Only invite if not already a member
        if not is_member:
            try:
                # Get or export invite link
                invite_link = await app.export_chat_invite_link(config.LOGGER_ID)
                await asyncio.sleep(0.5)
                
                # Assistant joins via invite link
                await client.join_chat(invite_link)
                logger.info(f"✓ Assistant '{client.name}' joined logs group")
                await asyncio.sleep(1)
            except Exception as e:
                err_str = str(e)
                if "USER_ALREADY_PARTICIPANT" in err_str:
                    logger.debug(f"✓ Assistant '{client.name}' is already a participant.")
                else:
                    logger.error(f"✗ Failed to invite '{client.name}': {e}")
        
        # Only promote if not already an admin
        if not is_admin:
            try:
                # Get Bot's privileges to know what we can grant
                me_member = await app.get_chat_member(config.LOGGER_ID, app.me.id)
                my_privileges = me_member.privileges
                
                if not my_privileges or not my_privileges.can_promote_members:
                    logger.error("⚠️ Bot needs 'Promote Members' permission in logs group!")
                    return

                # Promote with available permissions (similar to MissKatyPyro)
                await app.promote_chat_member(
                    config.LOGGER_ID,
                    client.id,
                    privileges=types.ChatPrivileges(
                        can_manage_chat=my_privileges.can_manage_chat,
                        can_delete_messages=my_privileges.can_delete_messages,
                        can_manage_video_chats=my_privileges.can_manage_video_chats,
                        can_restrict_members=my_privileges.can_restrict_members,
                        can_promote_members=False, # Don't let assistant promote others
                        can_change_info=False,
                        can_invite_users=my_privileges.can_invite_users,
                        can_pin_messages=my_privileges.can_pin_messages,
                    )
                )
                logger.info(f"✓ Promoted '{client.name}' as admin in logs group")
                await asyncio.sleep(1)  # Wait for Telegram to process
            except Exception as e:
                err_str = str(e)
                if "USER_CREATOR" in err_str:
                     logger.info(f"✓ Assistant '{client.name}' is the CREATOR of logs group (already admin)")
                elif "CHANNELS_ADMIN_PUBLIC_TOO_MUCH" in err_str:
                     logger.error(f"✗ Failed to promote '{client.name}': Too many public admins")
                elif "PEER_ID_INVALID" in err_str:
                     logger.warning(f"⚠️ Cannot promote '{client.name}' yet (Telegram hasn't fully registered the join). Will retry later naturally.")
                else:
                    logger.error(f"✗ Failed to promote '{client.name}': {e}")
        
        # Always try to send startup message if we just joined/verified
        try:
            await client.send_message(
                config.LOGGER_ID,
                f"✅ **Assistant Started**\n\n"
                f"**Name:** {client.user_name}\n"
                f"**Username:** @{client.username or 'None'}\n"
                f"**Session:** `{client.name}`"
            )
            logger.info(f"✓ Startup message sent by '{client.name}'")
        except Exception as e:
            logger.debug(f"Failed to send startup message for '{client.name}': {e}")
            
        client.log_setup_done = True

    async def invite_assistants_to_logs(self):
        """Invite all active assistants to logs group. Call this after bot is fully ready."""
        if not config.LOGGER_ID:
            return
            
        logger.info("Verifying assistants in logs group...")
        logger.info(f"Found {len(self.clients)} assistants to process")
        
        for client in self.clients:
             await self._setup_log_group(client)
        
        logger.info("Finished verifying assistants in logs group")


    async def exit(self):
        """Stop all assistant clients."""
        for client in self.clients[:]:
            try:
                await client.stop()
            except:
                pass
        self.clients.clear()
        self._client_map.clear()
        logger.info("All assistants stopped.")
