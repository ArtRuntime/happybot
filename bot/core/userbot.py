# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


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
        await client.start()
        
        # Set client properties first
        me = await client.get_me()
        client.id = me.id
        client.name = name  # Use our internal name
        client.user_name = me.first_name # Telegram name
        client.username = me.username
        client.mention = me.mention
        
        # Join and announce in logs group
        if config.LOGGER_ID:
            try:
                # Try to join the logs group
                await client.join_chat(config.LOGGER_ID)
                logger.info(f"Assistant '{name}' joined logs group")
            except Exception as e:
                logger.debug(f"Assistant '{name}' already in logs group or couldn't join: {e}")
            
            try:
                # Promote to admin so it can send messages
                from bot import app
                from pyrogram import types
                await app.promote_chat_member(
                    config.LOGGER_ID,
                    client.id,
                    privileges=types.ChatPrivileges(
                        can_manage_chat=False,
                        can_delete_messages=False,
                        can_manage_video_chats=False,
                        can_restrict_members=False,
                        can_promote_members=False,
                        can_change_info=False,
                        can_invite_users=False,
                        can_pin_messages=False,
                        can_post_messages=True,  # Allow posting
                    )
                )
                logger.info(f"Assistant '{name}' promoted in logs group")
            except Exception as e:
                logger.debug(f"Failed to promote assistant '{name}': {e}")
            
            try:
                # Send startup message from the assistant itself
                await client.send_message(
                    config.LOGGER_ID,
                    f"✅ **Assistant Started**\n\n"
                    f"**Name:** {client.user_name}\n"
                    f"**Username:** @{client.username or 'None'}\n"
                    f"**Session:** `{name}`"
                )
            except Exception as e:
                logger.error(f"Assistant '{name}' failed to send startup message: {e}")
        
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
        Perform auto-migration of env sessions.
        Note: We NO LONGER start all sessions here. They are lazy loaded.
        """
        from bot import db
        
        # Auto-migration: Check if any env sessions exist
        env_sessions = []
        if config.SESSION1:
            env_sessions.append(("SESSION1", config.SESSION1, "Assistant 1"))
        if config.SESSION2:
            env_sessions.append(("SESSION2", config.SESSION2, "Assistant 2"))
        if config.SESSION3:
            env_sessions.append(("SESSION3", config.SESSION3, "Assistant 3"))
        
        # Migrate env sessions to DB if they exist
        if env_sessions:
            logger.info("Found SESSION env vars, migrating to database...")
            for env_name, session_string, friendly_name in env_sessions:
                try:
                    # Check if already migrated
                    existing = await db.get_session_by_name(friendly_name)
                    if not existing:
                        await db.add_session(session_string, friendly_name, config.OWNER_ID)
                        logger.info(f"Migrated {env_name} to database as '{friendly_name}'")
                    else:
                        logger.info(f"{env_name} already migrated as '{friendly_name}'")
                except Exception as e:
                    logger.error(f"Failed to migrate {env_name}: {e}")
        
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
