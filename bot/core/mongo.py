# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from random import randint
from time import time
import asyncio

from pymongo import AsyncMongoClient

from bot import config, logger, userbot


class MongoDB:
    def __init__(self):
        """
        Initialize the MongoDB connection.
        """
        self.mongo = AsyncMongoClient(config.MONGO_URL, serverSelectionTimeoutMS=12500)
        self.db = self.mongo[config.MONGO_DB_NAME]

        # O(1) lookup structures
        self.admin_list = {}
        self.active_calls = {}
        self.admin_play = set()
        self.blacklisted_chats = set()
        self.blacklisted_users = set()
        self.cmd_delete = set()
        self.notified = set()
        
        self.cache = self.db.cache
        self.logger = False

        self.assistant = {} # Chat ID -> Assistant Name (String)
        self.assistantdb = self.db.assistant

        self.auth = {}
        self.authdb = self.db.auth

        self.chats = set()
        self.chatsdb = self.db.chats

        self.lang = {}
        self.langdb = self.db.lang

        self.users = set()
        self.usersdb = self.db.users
        
        self.autoplay = {}
        self.autoplaydb = self.db.autoplay
        
        # Sessions collection for dynamic assistant management
        self.sessions = []
        self.sessionsdb = self.db.sessions
        
        # Stream URL Cache
        self.stream_cache = self.db.stream_cache
        
        # Media Cache Metadata
        self.cache_metadata = self.db.cache_metadata

        # SangMata Collections
        self.sangmata_users = self.db.sangmata_users
        self.sangmata_chats = self.db.sangmata_chats

        # AFK Collection
        self.afk = self.db.afk

    async def connect(self) -> None:
        """Check if we can connect to the database and create indexes."""
        try:
            start = time()
            await self.mongo.admin.command("ping")
            logger.info(f"Database connection successful. ({time() - start:.2f}s)")
            
            # Create Indexes
            await self._create_indexes()
            
            await self.load_cache()
        except Exception as e:
            raise SystemExit(f"Database connection failed: {type(e).__name__}") from e

    async def _create_indexes(self):
        """Create necessary indexes for performance."""
        try:
            # Users & Chats
            # _id is automatically indexed and unique in MongoDB, so we don't need to create it explicitly
            
            # Sessions (Name must be unique)
            await self.sessionsdb.create_index("name", unique=True)
            
            logger.info("Database indexes verified/created.")
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")

    async def close(self) -> None:
        """Close the connection to the database."""
        await self.mongo.close()
        logger.info("Database connection closed.")

    # CACHE
    async def get_call(self, chat_id: int) -> bool:
        return chat_id in self.active_calls

    async def add_call(self, chat_id: int) -> None:
        self.active_calls[chat_id] = 1

    async def remove_call(self, chat_id: int) -> None:
        self.active_calls.pop(chat_id, None)

    async def playing(self, chat_id: int, paused: bool = None) -> bool | None:
        if paused is not None:
            self.active_calls[chat_id] = int(not paused)
        return bool(self.active_calls.get(chat_id, 0))

    async def get_admins(self, chat_id: int, reload: bool = False) -> list[int]:
        from bot.helpers._admins import reload_admins

        if chat_id not in self.admin_list or reload:
            self.admin_list[chat_id] = await reload_admins(chat_id)
        return self.admin_list[chat_id]

    # AUTH METHODS
    async def _get_auth(self, chat_id: int) -> set[int]:
        if chat_id not in self.auth:
            doc = await self.authdb.find_one({"_id": chat_id}) or {}
            self.auth[chat_id] = set(doc.get("user_ids", []))
        return self.auth[chat_id]

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return user_id in await self._get_auth(chat_id)

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id not in users:
            users.add(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$addToSet": {"user_ids": user_id}}, upsert=True
            )

    async def rm_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id in users:
            users.discard(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$pull": {"user_ids": user_id}}
            )

    # ASSISTANT METHODS - LAZY LOADING
    async def set_assistant(self, chat_id: int, session_name: str) -> str:
        """Assign a specific assistant (by name) to a chat."""
        await self.assistantdb.update_one(
            {"_id": chat_id},
            {"$set": {"name": session_name}},
            upsert=True,
        )
        self.assistant[chat_id] = session_name
        return session_name

    async def get_assistant(self, chat_id: int):
        """
        Get the assistant client for a chat.
        Starts the client if it's not running (Lazy Loading).
        """
        from bot import userbot
        
        if chat_id not in self.assistant:
            doc = await self.assistantdb.find_one({"_id": chat_id})
            if doc and "name" in doc:
                 # Use assigned name
                 name = doc["name"]
            else:
                 # Import app for checking group members
                 from bot import app
                 
                 # First, check if any assistant is already in this group
                 all_sessions = await self.get_all_sessions(include_inactive=False)
                 if not all_sessions:
                     logger.error("No active sessions available to assign!")
                     raise ValueError("No active sessions available")
                 
                 
                 existing_assistants = []  # List of (session_name, active_calls_count)
                 
                 # Check each assistant to see if they're already in the group
                 for session in all_sessions:
                     session_name = session["name"]
                     try:
                         # Get the userbot client for this session
                         ub_client = await userbot.get_client_by_name(session_name)
                         
                         # Check if this assistant is in the chat
                         try:
                             member = await app.get_chat_member(chat_id, ub_client.id)
                             # Assistant found in group!
                             # Count how many active calls this assistant has
                             active_calls = await self.db.calls.count_documents({"assistant": session_name})
                             existing_assistants.append((session_name, active_calls))
                             logger.debug(f"Found assistant '{session_name}' in chat {chat_id} with {active_calls} active calls")
                         except Exception:
                             # Not a member, continue checking
                             pass
                     except Exception as e:
                         logger.debug(f"Error checking session {session_name}: {e}")
                         continue
                 
                 if existing_assistants:
                     # Pick the assistant with the least active calls (least busy)
                     existing_assistants.sort(key=lambda x: x[1])  # Sort by active_calls count
                     name = existing_assistants[0][0]
                     active_calls_count = existing_assistants[0][1]
                     logger.info(f"Found {len(existing_assistants)} assistant(s) in chat {chat_id}, using '{name}' ({active_calls_count} active calls)")

                 else:
                     # No existing assistant found, assign one randomly
                     selected = all_sessions[randint(0, len(all_sessions) - 1)]
                     name = selected["name"]
                     logger.info(f"No existing assistant in chat {chat_id}, assigned '{name}'")
                 
                 await self.set_assistant(chat_id, name)
        
            self.assistant[chat_id] = name
        
        # Get name
        name = self.assistant[chat_id]
        
        # Ensure client is started (Lazy Load)
        await userbot.get_client_by_name(name)
        
        # Get PyTgCalls client
        from bot import anon
        return anon._client_map[name]

    async def get_client(self, chat_id: int):
        """
        Get the Pyrogram Userbot client for a chat.
        (Different from get_assistant which returns PyTgCalls client)
        """
        # Ensure assistant is assigned and started
        await self.get_assistant(chat_id)
        
        # Get name from cache
        name = self.assistant[chat_id]
        
        # Return Pyrogram client
        return await userbot.get_client_by_name(name)

    # BLACKLIST METHODS
    async def add_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted_chats.add(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"}, {"$addToSet": {"chat_ids": chat_id}}, upsert=True
            )
        self.blacklisted_users.add(chat_id)
        await self.cache.update_one(
            {"_id": "bl_users"}, {"$addToSet": {"user_ids": chat_id}}, upsert=True
        )

    async def del_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted_chats.discard(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"},
                {"$pull": {"chat_ids": chat_id}},
            )
        self.blacklisted_users.discard(chat_id)
        await self.cache.update_one(
            {"_id": "bl_users"},
            {"$pull": {"user_ids": chat_id}},
        )

    async def get_blacklisted(self, chat: bool = False) -> list[int]:
        if chat:
            if not self.blacklisted_chats:
                doc = await self.cache.find_one({"_id": "bl_chats"})
                if doc:
                    self.blacklisted_chats.update(doc.get("chat_ids", []) if doc else [])
            return list(self.blacklisted_chats)
            
        if not self.blacklisted_users:
            doc = await self.cache.find_one({"_id": "bl_users"})
            if doc:
                self.blacklisted_users.update(doc.get("user_ids", []))
        return list(self.blacklisted_users)

    # CHAT METHODS
    async def is_chat(self, chat_id: int) -> bool:
        return chat_id in self.chats

    async def add_chat(self, chat_id: int) -> None:
        if chat_id not in self.chats:
            self.chats.add(chat_id)
            try:
                await self.chatsdb.insert_one({"_id": chat_id})
            except:
                pass # Ignore duplicate key error

    async def rm_chat(self, chat_id: int) -> None:
        if chat_id in self.chats:
            self.chats.discard(chat_id)
            await self.chatsdb.delete_one({"_id": chat_id})

    async def get_chats(self) -> list:
        if not self.chats:
            async for chat in self.chatsdb.find():
                self.chats.add(chat["_id"])
        return list(self.chats)
    
    async def count_chats(self) -> int:
        """Fast count of total chats without loading all data"""
        return await self.chatsdb.count_documents({})

    # COMMAND DELETE
    async def get_cmd_delete(self, chat_id: int) -> bool:
        if chat_id not in self.cmd_delete:
            doc = await self.chatsdb.find_one({"_id": chat_id})
            if doc and doc.get("cmd_delete"):
                self.cmd_delete.add(chat_id)
        return chat_id in self.cmd_delete

    async def set_cmd_delete(self, chat_id: int, delete: bool = False) -> None:
        if delete:
            self.cmd_delete.add(chat_id)
        else:
            self.cmd_delete.discard(chat_id)
        await self.chatsdb.update_one(
            {"_id": chat_id},
            {"$set": {"cmd_delete": delete}},
            upsert=True,
        )

    # LANGUAGE METHODS
    async def set_lang(self, chat_id: int, lang_code: str):
        await self.langdb.update_one(
            {"_id": chat_id},
            {"$set": {"lang": lang_code}},
            upsert=True,
        )
        self.lang[chat_id] = lang_code

    async def get_lang(self, chat_id: int) -> str:
        if chat_id not in self.lang:
            doc = await self.langdb.find_one({"_id": chat_id})
            self.lang[chat_id] = doc["lang"] if doc else "en"
        return self.lang[chat_id]

    # AUTOPLAY METHODS
    async def set_autoplay(self, chat_id: int, status: str | bool):
        await self.autoplaydb.update_one(
            {"_id": chat_id},
            {"$set": {"status": status}},
            upsert=True,
        )
        self.autoplay[chat_id] = status

    async def get_autoplay(self, chat_id: int) -> str | bool:
        if chat_id not in self.autoplay:
            doc = await self.autoplaydb.find_one({"_id": chat_id})
            self.autoplay[chat_id] = doc["status"] if doc else False
        return self.autoplay[chat_id]

    # AUTO_LEAVE METHODS (per-chat override)
    async def set_auto_leave_enabled(self, chat_id: int, enabled: bool):
        """Set whether auto-leave is enabled for a specific chat. True = enabled (default), False = disabled."""
        await self.db.auto_leave.update_one(
            {"_id": chat_id},
            {"$set": {"enabled": enabled}},
            upsert=True,
        )

    async def get_auto_leave_enabled(self, chat_id: int) -> bool:
        """Get whether auto-leave is enabled for a specific chat. Returns True by default."""
        doc = await self.db.auto_leave.find_one({"_id": chat_id})
        return doc["enabled"] if doc else True  # Default: True (auto-leave enabled)

    # QUALITY METHODS
    async def set_quality(self, chat_id: int, quality: str):
        await self.db.quality.update_one(
            {"_id": chat_id},
            {"$set": {"quality": quality}},
            upsert=True,
        )

    async def get_quality(self, chat_id: int) -> str:
        doc = await self.db.quality.find_one({"_id": chat_id})
        return doc["quality"] if doc else "medium"


    # LOGGER METHODS
    async def is_logger(self) -> bool:
        return self.logger

    async def get_logger(self) -> bool:
        doc = await self.cache.find_one({"_id": "logger"})
        if doc:
            self.logger = doc["status"]
        return self.logger

    async def set_logger(self, status: bool) -> None:
        self.logger = status
        await self.cache.update_one(
            {"_id": "logger"},
            {"$set": {"status": status}},
            upsert=True,
        )

    # VC LOGGER PER-CHAT METHODS
    async def set_vc_logger_enabled(self, chat_id: int, enabled: bool):
        """Set whether VC logger is enabled for a specific chat. True=enabled, False=disabled."""
        await self.db.vc_logger.update_one(
            {"_id": chat_id},
            {"$set": {"enabled": enabled}},
            upsert=True,
        )

    async def get_vc_logger_enabled(self, chat_id: int) -> bool:
        """Get whether VC logger is enabled for a specific chat. Default: True"""
        doc = await self.db.vc_logger.find_one({"_id": chat_id})
        return doc["enabled"] if doc else False

    # PLAY MODE METHODS
    async def get_play_mode(self, chat_id: int) -> bool:
        if chat_id not in self.admin_play:
            doc = await self.chatsdb.find_one({"_id": chat_id})
            if doc and doc.get("admin_play"):
                self.admin_play.add(chat_id)
        return chat_id in self.admin_play

    async def set_play_mode(self, chat_id: int, remove: bool = False) -> None:
        if remove:
            self.admin_play.discard(chat_id)
        else:
            self.admin_play.add(chat_id)
        await self.chatsdb.update_one(
            {"_id": chat_id},
            {"$set": {"admin_play": not remove}},
            upsert=True,
        )

    # SUDO METHODS
    async def add_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$addToSet": {"user_ids": user_id}}, upsert=True
        )

    async def del_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$pull": {"user_ids": user_id}}
        )

    async def get_sudoers(self) -> list[int]:
        doc = await self.cache.find_one({"_id": "sudoers"})
        return doc.get("user_ids", []) if doc else []

    # USER METHODS
    async def is_user(self, user_id: int) -> bool:
        return user_id in self.users

    async def add_user(self, user_id: int) -> None:
        if user_id not in self.users:
            self.users.add(user_id)
            try:
                await self.usersdb.insert_one({"_id": user_id})
            except:
                pass

    async def rm_user(self, user_id: int) -> None:
        if user_id in self.users:
            self.users.discard(user_id)
            await self.usersdb.delete_one({"_id": user_id})

    async def get_users(self) -> list:
        if not self.users:
            async for user in self.usersdb.find():
                self.users.add(user["_id"])
        return list(self.users)
    
    async def count_users(self) -> int:
        """Fast count of total users without loading all data"""
        return await self.usersdb.count_documents({})


    async def migrate_coll(self) -> None:
        from bson import ObjectId
        logger.info("Migrating users and chats from old collections...")

        musers, mchats, done = [], [], set()
        ulist = [user async for user in self.db.tgusersdb.find()]
        ulist.extend([user async for user in self.usersdb.find()])

        for user in ulist:
            if isinstance(user.get("_id"), ObjectId):
                user_id = int(user["user_id"])
            else:
                user_id = int(user["_id"])
            
            if user_id not in done:
                done.add(user_id)
                musers.append({"_id": user_id})
                
        await self.usersdb.drop()
        await self.db.tgusersdb.drop()
        if musers:
            try:
                await self.usersdb.insert_many(musers, ordered=False)
            except:
                pass

        done.clear()
        async for chat in self.chatsdb.find():
            if isinstance(chat.get("_id"), ObjectId):
                chat_id = int(chat["chat_id"])
            else:
                chat_id = int(chat["_id"])
                
            if chat_id not in done:
                done.add(chat_id)
                mchats.append({"_id": chat_id})
                
        await self.chatsdb.drop()
        if mchats:
            try:
                await self.chatsdb.insert_many(mchats, ordered=False)
            except:
                pass

        await self.cache.insert_one({"_id": "migrated"})
        logger.info("Migration completed.")

    # SESSION METHODS
    async def get_sessions(self) -> list[dict]:
        """Get all active sessions from database."""
        if not self.sessions:
            sessions = []
            async for session in self.sessionsdb.find({"status": "active"}):
                 sessions.append(session)
            self.sessions = sessions
        return self.sessions

    async def get_all_sessions(self, include_inactive: bool = True) -> list[dict]:
        """Get all sessions from database, optionally including inactive ones."""
        query = {} if include_inactive else {"status": "active"}
        sessions = []
        async for session in self.sessionsdb.find(query).sort("added_at", -1):
            sessions.append(session)
        return sessions

    async def add_session(self, session_string: str, name: str, user_id: int) -> dict:
        """Add a new session to database."""
        from datetime import datetime
        
        # Check if name already exists
        existing = await self.sessionsdb.find_one({"name": name})
        if existing:
            raise ValueError(f"Session with name '{name}' already exists")
        
        session_doc = {
            "session_string": session_string,
            "name": name,
            "added_by": user_id,
            "added_at": datetime.now(),
            "status": "active"
        }
        
        result = await self.sessionsdb.insert_one(session_doc)
        session_doc["_id"] = result.inserted_id
        self.sessions.append(session_doc)
        return session_doc

    async def remove_session(self, name: str) -> bool:
        """Permanently delete a session from database."""
        # Delete the session document
        result = await self.sessionsdb.delete_one({"name": name})
        
        if result.deleted_count > 0:
            # Remove from cache
            self.sessions = [s for s in self.sessions if s["name"] != name]
            return True
        return False

    async def get_session_by_name(self, name: str) -> dict | None:
        """Get a specific session by name."""
        return await self.sessionsdb.find_one({"name": name, "status": "active"})

    async def load_cache(self) -> None:
        doc = await self.cache.find_one({"_id": "migrated"})
        if not doc:
            await self.migrate_coll()

        await self.get_chats()
        await self.get_users()
        await self.get_blacklisted(True)
        await self.get_logger()
        await self.get_sessions()  # Load sessions into cache
        logger.info("Database cache loaded.")
        
        # Validate cache files presence
        await self.validate_media_cache()

    async def validate_media_cache(self) -> None:
        """
        Validate all tracks in cache_metadata.
        If the physical file does not exist, remove the metadata from MongoDB.
        """
        import os
        removed_count = 0
        try:
            async for song in self.cache_metadata.find():
                file_path = song.get("file_path")
                if not file_path or not os.path.exists(file_path):
                    await self.cache_metadata.delete_one({"_id": song["_id"]})
                    removed_count += 1
            if removed_count > 0:
                logger.info(f"Cache validation complete: Removed {removed_count} stale cache records from database.")
        except Exception as e:
            logger.error(f"Error during cache validation: {e}")

    # STREAM CACHE METHODS
    async def add_stream_cache(self, video_id: str, url: str, expire: int) -> None:
        """
        Cache a stream URL with its expiration timestamp.
        """
        await self.stream_cache.update_one(
            {"_id": video_id},
            {"$set": {"url": url, "expire": expire}},
            upsert=True
        )

    async def get_stream_cache(self, video_id: str) -> dict | None:
        """
        Get cached stream URL if it exists.
        Returns dict with 'url' and 'expire' or None.
        """
        return await self.stream_cache.find_one({"_id": video_id})

    # CACHE CONFIGURATION & METADATA
    async def get_max_cache_limit(self) -> tuple[int, str]:
        """
        Get the current max cache limit from DB.
        Returns:
            tuple: (limit_in_bytes, limit_string)
        """
        doc = await self.cache.find_one({"_id": "max_cache_limit"})
        if doc:
            return doc.get("limit_bytes", 10 * 1024 * 1024 * 1024), doc.get("limit_str", "10.00 GB")
        # Default: 10 GB
        return 10 * 1024 * 1024 * 1024, "10.00 GB"

    async def set_max_cache_limit(self, limit_str: str) -> int:
        """
        Parse human readable limit string (e.g. '500MB', '10GB') and save it.
        Returns:
            int: The limit in bytes.
        """
        import re
        limit_str = limit_str.strip().upper()
        match = re.match(r"^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)?$", limit_str)
        if not match:
            raise ValueError("Invalid limit format. Use e.g. 500MB, 10GB.")
        
        value = float(match.group(1))
        unit = match.group(2) or "B"
        
        multiplier = {
            "B": 1,
            "KB": 1024,
            "MB": 1024 * 1024,
            "GB": 1024 * 1024 * 1024,
            "TB": 1024 * 1024 * 1024 * 1024
        }[unit]
        
        limit_bytes = int(value * multiplier)
        formatted_str = f"{value:.2f} {unit}"
        
        await self.cache.update_one(
            {"_id": "max_cache_limit"},
            {"$set": {"limit_bytes": limit_bytes, "limit_str": formatted_str}},
            upsert=True
        )
        return limit_bytes

    async def enforce_cache_limit(self, new_file_size: int = 0) -> None:
        """
        Sum all cached files in the database. If total exceeds limit,
        evict files based on LFU (play_count) then LRU (last_played_at) rules.
        """
        import os
        limit_bytes, _ = await self.get_max_cache_limit()
        
        # Calculate current tracked cache size
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$file_size"}}}]
        cursor = await self.cache_metadata.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        total_size = result[0]["total"] if result else 0
        
        if total_size + new_file_size <= limit_bytes:
            return
            
        logger.info(f"Cache limit exceeded ({total_size + new_file_size} / {limit_bytes} bytes). Enforcing eviction...")
        
        # Evict oldest & least played songs
        # Sort by play_count ASC (LFU) and last_played_at ASC (LRU)
        async for song in self.cache_metadata.find().sort([("play_count", 1), ("last_played_at", 1)]):
            file_path = song.get("file_path")
            file_size = song.get("file_size", 0)
            
            # Physically delete the file
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Evicted file from cache: {file_path} (saved {file_size} bytes)")
                except Exception as e:
                    logger.error(f"Failed to delete evicted file {file_path}: {e}")
            
            # Remove from DB
            await self.cache_metadata.delete_one({"_id": song["_id"]})
            
            total_size -= file_size
            if total_size + new_file_size <= limit_bytes:
                break
        
        logger.info(f"Eviction complete. Current cache size: {total_size} bytes.")

    async def register_cache_play(self, media) -> None:
        """
        Registers a play event for a media object, updating its statistics in the database.
        Runs cache limit checks.
        """
        import os
        from datetime import datetime
        
        if not media or not media.file_path or media.file_path.startswith("http"):
            return # Don't cache network streams or empty paths
            
        try:
            file_size = 0
            if os.path.exists(media.file_path):
                file_size = os.path.getsize(media.file_path)
            
            # Upsert into cache_metadata
            await self.cache_metadata.update_one(
                {"_id": media.id},
                {
                    "$set": {
                        "file_path": media.file_path,
                        "title": media.title,
                        "format": "video" if getattr(media, "video", False) else "audio",
                        "file_size": file_size,
                        "last_played_at": datetime.now(),
                    },
                    "$inc": {"play_count": 1}
                },
                upsert=True
            )
            
            # Enforce limits after recording
            await self.enforce_cache_limit()
        except Exception as e:
            logger.error(f"Failed to register cache play for {media.title}: {e}")

    # FEDERATION METHODS
    async def create_fed(self, fed_name, user_id, fed_id):
        return await self.db.feds.insert_one(
            {
                "fed_id": str(fed_id),
                "fed_name": str(fed_name),
                "owner_id": int(user_id),
                "fadmins": [],
                "owner_mention": "",
                "banned_users": [],
                "chat_ids": [],
                "log_group_id": config.LOGGER_ID,
            }
        )

    async def get_fed_info(self, fed_id):
        return await self.db.feds.find_one({"fed_id": str(fed_id)})

    async def get_feds_by_owner(self, owner_id):
        return [fed async for fed in self.db.feds.find({"owner_id": int(owner_id)})]

    async def del_fed(self, fed_id):
        return await self.db.feds.delete_one({"fed_id": str(fed_id)})

    async def fed_rename(self, fed_id, newname):
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id)},
            {"$set": {"fed_name": str(newname)}},
        )

    async def transfer_owner(self, fed_id, current_owner, new_owner):
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id), "owner_id": int(current_owner)},
            {"$set": {"owner_id": int(new_owner)}},
        )

    async def search_user_in_fed(self, fed_id, user_id):
        fed = await self.db.feds.find_one({"fed_id": str(fed_id)})
        return user_id in fed.get("fadmins", []) if fed else False

    async def user_join_fed(self, fed_id, user_id):
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id)},
            {"$addToSet": {"fadmins": int(user_id)}},
        )

    async def user_demote_fed(self, fed_id, user_id):
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id)},
            {"$pull": {"fadmins": int(user_id)}},
        )

    async def search_fed_by_id(self, fed_id):
        return await self.db.feds.find_one({"fed_id": str(fed_id)})

    async def chat_join_fed(self, fed_id, chat_title, chat_id):
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id)},
            {"$addToSet": {"chat_ids": str(chat_id)}},
        )

    async def chat_leave_fed(self, chat_id):
        # This is inefficient but functional for small scale
        # Ideally we store fed_id in chat document too
        async for fed in self.db.feds.find():
            if str(chat_id) in fed.get("chat_ids", []):
                return await self.db.feds.update_one(
                    {"fed_id": fed["fed_id"]},
                    {"$pull": {"chat_ids": str(chat_id)}},
                )
        return False

    async def get_fed_id(self, chat_id):
        async for fed in self.db.feds.find():
            if str(chat_id) in fed.get("chat_ids", []):
                return fed["fed_id"]
        return None

    async def add_fban_user(self, fed_id, user_id, reason):
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id)},
            {
                "$push": {
                    "banned_users": {
                        "user_id": int(user_id),
                        "reason": str(reason),
                        "date": int(time()),
                    }
                }
            },
        )

    async def remove_fban_user(self, fed_id, user_id):
        fed = await self.db.feds.find_one({"fed_id": str(fed_id)})
        if not fed:
            return False
        new_banned = [u for u in fed.get("banned_users", []) if u["user_id"] != int(user_id)]
        return await self.db.feds.update_one(
            {"fed_id": str(fed_id)},
            {"$set": {"banned_users": new_banned}},
        )

    async def check_banned_user(self, fed_id, user_id):
        fed = await self.db.feds.find_one({"fed_id": str(fed_id)})
        if not fed:
            return False
        for user in fed.get("banned_users", []):
            if user["user_id"] == int(user_id):
                return user
        return False


    # AUTO APPROVE METHODS
    async def set_auto_approve(self, chat_id: int, status: bool):
        await self.db.auto_approve.update_one(
            {"_id": chat_id},
            {"$set": {"status": status}},
            upsert=True,
        )

    async def get_auto_approve(self, chat_id: int) -> bool:
        doc = await self.db.auto_approve.find_one({"_id": chat_id})
        return doc["status"] if doc else False


    # CHAT BLACKLIST FILTERS (Word Blacklist)
    async def add_chat_filter(self, chat_id: int, word: str):
        await self.db.chat_filters.update_one(
            {"_id": chat_id},
            {"$addToSet": {"filters": str(word)}},
            upsert=True,
        )

    async def remove_chat_filter(self, chat_id: int, word: str):
        await self.db.chat_filters.update_one(
            {"_id": chat_id},
            {"$pull": {"filters": str(word)}},
        )

    async def get_chat_filters(self, chat_id: int) -> list[str]:
        doc = await self.db.chat_filters.find_one({"_id": chat_id})
        return doc["filters"] if doc else []


    # FILTERS (Auto-Reply)
    async def save_filter(self, chat_id: int, name: str, _filter: dict):
        name = name.lower().strip()
        _filter["name"] = name
        await self.db.filters.update_one(
            {"chat_id": chat_id, "name": name},
            {"$set": _filter},
            upsert=True,
        )

    async def get_filter(self, chat_id: int, name: str) -> dict | None:
        name = name.lower().strip()
        return await self.db.filters.find_one({"chat_id": chat_id, "name": name})

    async def get_filters_names(self, chat_id: int) -> list[str]:
        return [
            doc["name"]
            async for doc in self.db.filters.find({"chat_id": chat_id})
        ]

    async def delete_filter(self, chat_id: int, name: str) -> bool:
        name = name.lower().strip()
        result = await self.db.filters.delete_one({"chat_id": chat_id, "name": name})
        return result.deleted_count > 0

    async def deleteall_filters(self, chat_id: int) -> bool:
        result = await self.db.filters.delete_many({"chat_id": chat_id})
        return result.deleted_count > 0


    # AUTO FORWARD METHODS
    async def add_forward(self, source_id: int, dest_id: int):
        await self.db.forwards.update_one(
            {"_id": source_id},
            {"$addToSet": {"dests": dest_id}},
            upsert=True,
        )

    async def remove_forward(self, source_id: int, dest_id: int):
        await self.db.forwards.update_one(
            {"_id": source_id},
            {"$pull": {"dests": dest_id}},
        )

    async def get_forwards(self, source_id: int) -> list[int]:
        doc = await self.db.forwards.find_one({"_id": source_id})
        return doc["dests"] if doc else []

    async def get_all_forward_sources(self):
        # Useful for caching if needed
        return [doc["_id"] async for doc in self.db.forwards.find()]

    # SANGMATA METHODS
    async def update_sangmata_user(self, user_id: int, username: str, first_name: str, last_name: str):
        await self.sangmata_users.update_one(
            {"_id": user_id},
            {"$set": {"username": username, "first_name": first_name, "last_name": last_name}},
            upsert=True
        )

    async def get_sangmata_user(self, user_id: int):
        doc = await self.sangmata_users.find_one({"_id": user_id})
        if doc:
            return doc.get("username"), doc.get("first_name"), doc.get("last_name")
        return None, None, None

    async def set_sangmata_status(self, chat_id: int, status: bool):
        await self.sangmata_chats.update_one(
            {"_id": chat_id},
            {"$set": {"enabled": status}},
            upsert=True
        )

    async def is_sangmata_on(self, chat_id: int) -> bool:
        doc = await self.sangmata_chats.find_one({"_id": chat_id})
        return doc and doc.get("enabled", False)

    # AFK METHODS
    async def add_afk(self, user_id: int, details: dict):
        await self.afk.update_one(
            {"_id": user_id},
            {"$set": details},
            upsert=True
        )

    async def remove_afk(self, user_id: int):
        await self.afk.delete_one({"_id": user_id})

    async def is_afk(self, user_id: int):
        doc = await self.afk.find_one({"_id": user_id})
        if doc:
            return True, doc
        return False, {}
