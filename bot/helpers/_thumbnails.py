# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


import os
import aiohttp
from PIL import (Image, ImageDraw, ImageEnhance,
                 ImageFilter, ImageFont, ImageOps)

from bot import config
from bot.helpers import Track


class Thumbnail:
    def __init__(self):
        self.rect = (914, 514)
        self.fill = (255, 255, 255)
        self.mask = Image.new("L", self.rect, 0)
        self.font1 = ImageFont.load_default()
        self.font2 = ImageFont.load_default()

    async def save_thumb(self, output_path: str, url: str) -> str:
        # Proxy Logic
        # Same as youtube.py: Use SOCKS connector if socks, else pass proxy arg
        session = None
        try:
            if config.PROXY_URL and config.PROXY_URL.startswith("socks"):
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(config.PROXY_URL)
                session = aiohttp.ClientSession(connector=connector)
            else:
                session = aiohttp.ClientSession()
            
            async with session:
                kwargs = {}
                if config.PROXY_URL and not config.PROXY_URL.startswith("socks"):
                    kwargs["proxy"] = config.PROXY_URL
                    
                async with session.get(url, **kwargs) as resp:
                    resp.raise_for_status()
                    open(output_path, "wb").write(await resp.read())
        except Exception as e:
            from bot import logger
            logger.error(f"Failed to save thumbnail: {e}")
            pass
        finally:
             if session: await session.close()
        return output_path

    async def generate(self, song: Track, size=(1280, 720)) -> str:
        try:
            # Create cache directory if it doesn't exist
            os.makedirs("cache", exist_ok=True)
            
            # Sanitize filename - remove invalid characters from URL
            import hashlib
            safe_id = hashlib.md5(song.id.encode()).hexdigest()[:16]
            temp = f"cache/temp_{safe_id}.jpg"
            output = f"cache/{safe_id}.png"
            if os.path.exists(output):
                return output

            # Fallback: Use YouTube default thumbnail if ytmusicapi thumbnail is missing
            thumbnail_url = song.thumbnail
            if not thumbnail_url or thumbnail_url == "":
                from bot import logger
                logger.info(f"Thumbnail URL missing for {song.title}, using YouTube default")
                
                # Try multiple YouTube thumbnail qualities (maxres not always available)
                thumbnail_qualities = [
                    f"https://img.youtube.com/vi/{song.id}/maxresdefault.jpg",
                    f"https://img.youtube.com/vi/{song.id}/hqdefault.jpg",
                    f"https://img.youtube.com/vi/{song.id}/mqdefault.jpg",
                    f"https://img.youtube.com/vi/{song.id}/default.jpg"
                ]
                
                # Try each quality until one works
                for quality_url in thumbnail_qualities:
                    try:
                        await self.save_thumb(temp, quality_url)
                        if os.path.exists(temp):
                            break
                    except:
                        continue
            else:
                await self.save_thumb(temp, thumbnail_url)
            
            if not os.path.exists(temp):
                from bot import logger
                logger.error(f"All thumbnail download attempts failed for {song.title}")
                return config.DEFAULT_THUMB
            thumb = Image.open(temp).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
            blur = thumb.filter(ImageFilter.GaussianBlur(25))
            image = ImageEnhance.Brightness(blur).enhance(.40)

            _rect = ImageOps.fit(thumb, self.rect, method=Image.LANCZOS, centering=(0.5, 0.5))
            ImageDraw.Draw(self.mask).rounded_rectangle((0, 0, self.rect[0], self.rect[1]), radius=15, fill=255)
            _rect.putalpha(self.mask)
            image.paste(_rect, (183, 30), _rect)

            draw = ImageDraw.Draw(image)
            draw.text((50, 560), f"{(song.channel_name or 'Unknown')[:25]} | {song.view_count or ''}", font=self.font2, fill=self.fill)
            draw.text((50, 600), (song.title or 'Unknown')[:50], font=self.font1, fill=self.fill)
            draw.text((40, 650), "0:01", font=self.font1)
            draw.line([(140, 670), (1160, 670)], fill=self.fill, width=5, joint="curve")
            draw.text((1185, 650), song.duration, font=self.font1, fill=self.fill)

            image.save(output)
            os.remove(temp)
            return output
        except:
            return config.DEFAULT_THUMB
