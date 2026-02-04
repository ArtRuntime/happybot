# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

import asyncio
import json
import os
from bot import logger

async def get_audio_streams(file_path: str) -> list[dict]:
    """
    Use ffprobe to detect all audio streams in a media file.
    
    Returns:
        List of dicts with 'index', 'language', 'title' for each audio stream
    """
    if not file_path or not os.path.exists(file_path):
        return []
    
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "a",  # Audio streams only
            file_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            logger.error(f"ffprobe failed: {stderr.decode()}")
            return []
        
        data = json.loads(stdout.decode())
        streams = data.get("streams", [])
        
        audio_tracks = []
        for idx, stream in enumerate(streams):
            tags = stream.get("tags", {})
            language = tags.get("language", "unknown")
            title = tags.get("title", f"Track {idx + 1}")
            
            audio_tracks.append({
                "index": idx,
                "language": language,
                "title": title,
                "codec": stream.get("codec_name", "unknown")
            })
        
        return audio_tracks
        
    except Exception as e:
        logger.error(f"Error detecting audio streams: {e}")
        return []
