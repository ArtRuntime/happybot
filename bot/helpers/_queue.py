# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import json
import redis.asyncio as redis
from dataclasses import asdict
from typing import Union

from bot import config
from ._dataclass import Media, Track

MediaItem = Union[Media, Track]


class Queue:
    def __init__(self):
        # We assume config.REDIS_URL is available
        self.rds = redis.from_url(config.REDIS_URL, decode_responses=True)

    @staticmethod
    def _to_json(item: MediaItem) -> str:
        data = {}
        if isinstance(item, Media):
            data = {
                "id": item.id,
                "duration": item.duration,
                "duration_sec": item.duration_sec,
                "file_path": item.file_path,
                "message_id": item.message_id,
                "title": item.title,
                "url": item.url,
                "time": item.time,
                "user": str(item.user) if item.user else None,
                "video": item.video,
                "req_type": item.req_type,
                "played_at": item.played_at,
                "_type": "Media"
            }
        elif isinstance(item, Track):
            data = {
                "id": item.id,
                "channel_name": item.channel_name,
                "duration": item.duration,
                "duration_sec": item.duration_sec,
                "title": item.title,
                "url": item.url,
                "file_path": item.file_path,
                "message_id": item.message_id,
                "time": item.time,
                "thumbnail": item.thumbnail,
                "user": str(item.user) if item.user else None,
                "view_count": item.view_count,
                "video": item.video,
                "req_type": item.req_type,
                "played_at": item.played_at,
                "_type": "Track"
            }
        return json.dumps(data)

    @staticmethod
    def _from_json(data: str) -> MediaItem | None:
        if not data:
            return None
        try:
            d = json.loads(data)
            type_ = d.pop("_type", None)
            if type_ == "Media":
                return Media(**d)
            elif type_ == "Track":
                return Track(**d)
            return None
        except:
            return None

    async def add(self, chat_id: int, item: MediaItem) -> int:
        """Add an item to the queue and return its position (1-based)."""
        json_item = self._to_json(item)
        
        # Check if queue is empty to set current playing immediately
        # Note: In Redis strict queue logic, we just push.
        # But legacy logic did: if empty -> set current.
        # We will check if "current" key exists.
        
        # NOTE: Legacy logic was:
        # queues[chat_id].append(item)
        # if len == 1: current = item
        
        # Redis Logic:
        # If current is empty, set it. Else add to queue list.
        current = await self.rds.get(f"current:{chat_id}")
        if not current:
             await self.rds.set(f"current:{chat_id}", json_item)
             return 0  # 0 indicates it's playing now (conceptually)
        else:
             pos = await self.rds.rpush(f"queue:{chat_id}", json_item)
             return pos

    async def check_item(self, chat_id: int, item_id: str) -> tuple[int, MediaItem | None]:
        """Check if an item with the given ID exists in the queue."""
        items = await self.rds.lrange(f"queue:{chat_id}", 0, -1)
        for i, data in enumerate(items):
            item = self._from_json(data)
            if item and item.id == item_id:
                return i, item
        return -1, None

    async def force_add(
        self, chat_id: int, item: MediaItem, remove: int | bool = False
    ) -> None:
        """Replace the currently playing item with a new one."""
        # 1. Clear current
        # 2. Add new item to LEFT of queue (or set as current)
        # Legacy: rotate to remove `remove` items
        
        json_item = self._to_json(item)
        
        # Set as current
        await self.rds.set(f"current:{chat_id}", json_item)
        
        if remove:
            # Pop `remove` items from LEFT
             for _ in range(int(remove)):
                 await self.rds.lpop(f"queue:{chat_id}")
                 
        # Actually force_play usually means stop current, play this.
        # We set `current`. Queue remains. 
        # If we want to simulate `appendleft`, we LPUSH.
        await self.rds.lpush(f"queue:{chat_id}", json_item)

    async def insert_front(self, chat_id: int, item: MediaItem) -> None:
        """Insert an item to the front of the queue (play next)."""
        json_item = self._to_json(item)
        await self.rds.lpush(f"queue:{chat_id}", json_item)


    async def get_current(self, chat_id: int) -> MediaItem | None:
        """Return the currently playing item."""
        data = await self.rds.get(f"current:{chat_id}")
        return self._from_json(data)

    async def update_current(self, chat_id: int, item: MediaItem) -> None:
        """Update the currently playing item (e.g. adding message_id)."""
        json_item = self._to_json(item)
        await self.rds.set(f"current:{chat_id}", json_item)

    async def get_next(self, chat_id: int, check: bool = False) -> MediaItem | None:
        """Remove current item and return the next one, or None if empty."""
        # If just checking next item
        if check:
            data = await self.rds.lindex(f"queue:{chat_id}", 0)
            return self._from_json(data)

        # Move next item from queue to current
        data = await self.rds.lpop(f"queue:{chat_id}")
        if data:
            await self.rds.set(f"current:{chat_id}", data)
            return self._from_json(data)
        else:
            # Queue empty
            await self.rds.delete(f"current:{chat_id}")
            return None

    async def get_playing(self, chat_id: int) -> MediaItem | None:
        """Return the currently playing item (same as get_current)."""
        return await self.get_current(chat_id)

    async def get_queue(self, chat_id: int) -> list[MediaItem]:
        """Return the full queue including the currently playing item."""
        current = await self.get_current(chat_id)
        items = []
        if current:
            items.append(current)
            
        queue_data = await self.rds.lrange(f"queue:{chat_id}", 0, -1)
        for data in queue_data:
            item = self._from_json(data)
            if item:
                items.append(item)
        return items

    async def remove_current(self, chat_id: int) -> None:
        """Remove the currently playing item key."""
        await self.rds.delete(f"current:{chat_id}")

    async def clear(self, chat_id: int) -> None:
        """Clear the entire queue and current."""
        await self.rds.delete(f"queue:{chat_id}")
        await self.rds.delete(f"current:{chat_id}")
