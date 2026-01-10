# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import Client

from bot import config, logger


class Userbot(Client):
    def __init__(self):
        """
        Initializes the userbot with dynamic session loading from MongoDB.
        """
        self.clients = []
        self._client_map = {}  # Maps session name to client instance

    async def _create_client(self, session_string: str, name: str) -> Client:
        """Create a new Pyrogram client from session string."""
        client = Client(
            name=f"bot_{name}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=session_string,
            proxy=config.PROXY_DICT,
        )
        return client

    async def add_client(self, session_string: str, name: str) -> Client:
        """
        Dynamically add a new client (hot-reload).
        
        Args:
            session_string: Pyrogram session string
            name: Unique identifier for this session
            
        Returns:
            The started client instance
        """
        if name in self._client_map:
            raise ValueError(f"Client with name '{name}' already exists")
        
        client = await self._create_client(session_string, name)
        await client.start()
        
        try:
            await client.send_message(config.LOGGER_ID, f"Assistant '{name}' Started")
        except Exception as e:
            logger.error(f"Assistant '{name}' failed to send message in log group: {e}")
            await client.stop()
            raise
        
        # Set client properties
        me = await client.get_me()
        client.id = me.id
        client.name = me.first_name
        client.username = me.username
        client.mention = me.mention
        
        self.clients.append(client)
        self._client_map[name] = client
        
        try:
            await client.join_chat("FallenAssociation")
        except:
            pass
        
        logger.info(f"Assistant '{name}' started as @{client.username}")
        return client

    async def remove_client(self, name: str) -> bool:
        """
        Dynamically remove a client (hot-reload).
        
        Args:
            name: Session name to remove
            
        Returns:
            True if removed, False if not found
        """
        if name not in self._client_map:
            return False
        
        client = self._client_map[name]
        
        # Stop the client
        try:
            await client.stop()
        except:
            pass
        
        # Remove from lists
        self.clients.remove(client)
        del self._client_map[name]
        
        logger.info(f"Assistant '{name}' stopped and removed")
        return True

    async def boot(self):
        """
        Load and start all active sessions from database and .env.
        Performs auto-migration of env sessions to DB.
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
        
        # Load all active sessions from database
        sessions = await db.get_sessions()
        if not sessions:
            logger.warning("No active sessions found in database!")
            return
        
        logger.info(f"Loading {len(sessions)} session(s) from database...")
        for session_doc in sessions:
            try:
                await self.add_client(
                    session_doc["session_string"],
                    session_doc["name"]
                )
            except Exception as e:
                logger.error(f"Failed to load session '{session_doc['name']}': {e}")

    async def exit(self):
        """Stop all assistant clients."""
        for client in self.clients[:]:  # Use slice to avoid modification during iteration
            try:
                await client.stop()
            except:
                pass
        self.clients.clear()
        self._client_map.clear()
        logger.info("All assistants stopped.")
