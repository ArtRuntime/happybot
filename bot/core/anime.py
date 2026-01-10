# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import httpx
from typing import Dict, List, Optional

from bot import config, logger


class AnimeAPI:
    def __init__(self):
        self.base_url = config.ANIME_API_URL
        self.client = httpx.AsyncClient(timeout=30.0)

    async def search_anime(self, query: str) -> Optional[List[Dict]]:
        """Search for anime by name."""
        try:
            url = f"{self.base_url}/api/search"
            params = {"keyword": query}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"Search API response: {data}")
            
            if data.get("success"):
                results = data.get("results", [])
                
                # Handle if results is a dict (some endpoints return nested structure)
                if isinstance(results, dict):
                    # Try to extract list from common keys
                    results = results.get("data", results.get("animes", []))
                
                # Ensure it's a list
                if not isinstance(results, list):
                    logger.error(f"Unexpected results type: {type(results)}")
                    return []
                
                return results
            return None
        except Exception as e:
            logger.error(f"Anime search failed: {e}")
            return None

    async def get_anime_info(self, anime_id: str) -> Optional[Dict]:
        """Get detailed information about an anime."""
        try:
            url = f"{self.base_url}/api/info"
            params = {"id": anime_id}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("success"):
                return data.get("results", {})
            return None
        except Exception as e:
            logger.error(f"Failed to get anime info: {e}")
            return None

    async def get_episodes(self, anime_id: str) -> Optional[Dict]:
        """Get list of episodes for an anime."""
        try:
            url = f"{self.base_url}/api/episodes/{anime_id}"
            
            response = await self.client.get(url)
            response.raise_for_status()
            
            data = response.json()
            if data.get("success"):
                return data.get("results", {})
            return None
        except Exception as e:
            logger.error(f"Failed to get episodes: {e}")
            return None

    async def get_stream(
        self,
        anime_id: str,
        episode_id: str,
        server: str = "hd-1",
        stream_type: str = "sub"
    ) -> Optional[Dict]:
        """Get streaming link for an episode."""
        try:
            url = f"{self.base_url}/api/stream"
            params = {
                "id": f"{anime_id}?ep={episode_id}",
                "server": server,
                "type": stream_type
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("success"):
                return data.get("results", {})
            return None
        except Exception as e:
            logger.error(f"Failed to get stream: {e}")
            return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
