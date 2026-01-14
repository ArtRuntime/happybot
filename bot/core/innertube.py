import json
import os
import http.cookiejar
import aiohttp
import asyncio
from typing import Optional, Dict
from bot import config, logger

class InnerTube:
    def __init__(self):
        self.cookies_path = "bot/cookies/cookies.txt"
        self.url = "https://www.youtube.com/youtubei/v1/player"
        self.context = {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.29.35",
                "androidSdkVersion": 30,
                "userAgent": "com.google.android.youtube/19.29.35 (Linux; U; Android 11) gzip",
                "hl": "en",
                "gl": "US",
                "utcOffsetMinutes": 0
            }
        }

    def _load_cookies(self) -> Dict:
        """Loads cookies from the Netscape format file into a dictionary."""
        if not os.path.exists(self.cookies_path):
            logger.warning(f"InnerTube: '{self.cookies_path}' not found. Running without login.")
            return {}

        try:
            jar = http.cookiejar.MozillaCookieJar(self.cookies_path)
            jar.load(ignore_discard=True, ignore_expires=True)
            cookies = {cookie.name: cookie.value for cookie in jar}
            # logger.info("InnerTube: Cookies loaded successfully.")
            return cookies
        except Exception as e:
            logger.error(f"InnerTube: Error loading cookies: {e}")
            return {}

    async def get_stream_info(self, video_id: str) -> Optional[Dict]:
        """
        Fetches stream info using InnerTube API.
        Returns a dict with 'url', 'title', 'duration', etc., or None if failed.
        """
        payload = {
            "videoId": video_id,
            "context": self.context
        }
        cookies = await asyncio.to_thread(self._load_cookies)

        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.post(self.url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"InnerTube: API returned {response.status}")
                        return None
                    
                    data = await response.json()

            if 'streamingData' not in data:
                status = data.get('playabilityStatus', {}).get('status', 'UNKNOWN')
                reason = data.get('playabilityStatus', {}).get('reason', 'Unknown reason')
                logger.warning(f"InnerTube: No streamingData. Status: {status}, Reason: {reason}")
                return None

            formats = data['streamingData'].get('formats', [])
            stream_url = None
            
            # Prefer itag 18 (360p) for reliability
            for fmt in formats:
                if fmt.get('itag') == 18:
                    stream_url = fmt['url']
                    break
            
            # Fallback to first available format
            if not stream_url and formats:
                stream_url = formats[0]['url']
                
            if not stream_url:
                logger.warning("InnerTube: No valid stream URL found.")
                return None

            # Extract basic metadata
            video_details = data.get('videoDetails', {})
            title = video_details.get('title', 'Unknown Title')
            duration_sec = int(video_details.get('lengthSeconds', 0))
            
            return {
                "url": stream_url,
                "title": title,
                "duration_sec": duration_sec,
                "video_id": video_id
            }

        except Exception as e:
            logger.error(f"InnerTube: Error fetching stream info: {e}")
            return None

    async def download(self, video_id: str, output_path: str = None) -> Optional[str]:
        """
        Downloads a video/audio stream to a file.
        Returns the file path on success, or None on failure.
        """
        info = await self.get_stream_info(video_id)
        if not info:
            return None

        url = info['url']
        if not output_path:
            # Create a simple filename if none provided
            output_path = f"downloads/{video_id}.mp4"
            
        cookies = await asyncio.to_thread(self._load_cookies)
        
        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(url) as response:
                    if response.status == 403:
                        logger.error("InnerTube: Download 403 Forbidden.")
                        return None
                    
                    if response.status != 200:
                        logger.error(f"InnerTube: Download failed with {response.status}")
                        return None
                    
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    with open(output_path, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                            
            logger.info(f"InnerTube: Download complete -> {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"InnerTube: Download error: {e}")
            return None

# Singleton instance
innertube = InnerTube()
