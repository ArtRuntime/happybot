import os
import asyncio
from pyrogram import filters
from pyrogram.types import Message
from bot import app, config
from bot.helpers.feds_utils import capture_err

__MODULE__ = "Video Downloader"
__HELP__ = """
**Video Downloader:**

/ytdl <url> - Download video/audio from any yt-dlp supported site
/ytdl <url> audio - Download audio only

Supports: YouTube, Twitter, Instagram, TikTok, Facebook, and 1000+ sites.
"""

async def run_ytdl(url: str, audio_only: bool = False):
    """Run yt-dlp with 3-step cookie fallback and return the downloaded file path"""
    output_template = "downloads/%(title).50s.%(ext)s"
    
    if audio_only:
        base_cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",  # Fallback to best if bestaudio not available
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
        ]
    else:
        # Smart format selection with fallback
        # Try: 720p → best video+audio → best available
        base_cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best",
            "-o", output_template,
            "--merge-output-format", "mp4",  # Ensure compatible format
        ]
    
    # 3-step fallback strategy
    cookie_strategies = [
        ("bot/cookies/cookies.txt", "primary cookies"),
        ("bot/cookies/fallback.txt", "fallback cookies"),
        (None, "no cookies")
    ]
    
    last_error = None
    
    for cookie_file, strategy_name in cookie_strategies:
        cmd = base_cmd.copy()
        cmd.append(url)
        
        # Add cookies if available for this strategy
        if cookie_file and os.path.exists(cookie_file):
            cmd.insert(-1, "--cookies")
            cmd.insert(-1, cookie_file)
            print(f"[ytdl] Trying with {strategy_name}: {cookie_file}")
        elif cookie_file:
            # Cookie file specified but doesn't exist, skip this strategy
            continue
        else:
            print(f"[ytdl] Trying with {strategy_name}")
        
        # Use the same proxy as the bot for consistency
        # This allows Instagram and other sites to work through the VPN
        from bot import config
        if config.PROXY_URL:
            cmd.insert(-1, "--proxy")
            cmd.insert(-1, config.PROXY_URL)
            print(f"[ytdl] Using proxy: {config.PROXY_URL}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        
        if proc.returncode == 0:
            # Success! Parse output to find downloaded file
            output = stdout.decode().strip()
            for line in output.split('\n'):
                if 'Destination:' in line or 'has already been downloaded' in line:
                    # Extract filename from line
                    parts = line.split(']')
                    if len(parts) > 1:
                        filepath = parts[-1].strip()
                        if os.path.exists(filepath):
                            print(f"[ytdl] ✓ Success with {strategy_name}")
                            return filepath
            
            # Fallback: search downloads directory for most recent file
            downloads = []
            for f in os.listdir("downloads"):
                path = os.path.join("downloads", f)
                if os.path.isfile(path):
                    downloads.append((os.path.getmtime(path), path))
            
            if downloads:
                downloads.sort(reverse=True)
                print(f"[ytdl] ✓ Success with {strategy_name} (found via directory scan)")
                return downloads[0][1]
        else:
            # Failed, save error and try next strategy
            error = stderr.decode().strip()
            last_error = error
            print(f"[ytdl] ✗ Failed with {strategy_name}: {error[:100]}")
    
    # All strategies failed - provide helpful error message
    if "Failed to resolve" in last_error or "No address associated with hostname" in last_error:
        raise Exception(
            "Network/DNS error: Cannot reach the website. "
            "This might be due to VPN/proxy blocking the site or DNS issues. "
            "Try a different URL or check your network connection."
        )
    elif "No csrf token" in last_error:
        raise Exception(
            "Instagram authentication failed. The site may be blocking automated downloads. "
            "Try again later or use a different link."
        )
    else:
        raise Exception(f"yt-dlp failed with all strategies. Last error: {last_error}")


@app.on_message(filters.command("ytdl") & filters.group)
@capture_err
async def ytdl_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /ytdl <url> [audio]")
    
    url = message.command[1]
    audio_only = len(message.command) > 2 and message.command[2].lower() == "audio"
    
    # Check if user is admin or sudo
    member = await app.get_chat_member(message.chat.id, message.from_user.id)
    from pyrogram.enums import ChatMemberStatus
    
    is_admin = member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    sudoers = await client.db.get_sudoers() if hasattr(client, 'db') else []
    is_sudo = message.from_user.id in sudoers or message.from_user.id == config.OWNER_ID
    
    if not (is_admin or is_sudo):
        return await message.reply_text("Only admins can use this command.")
    
    status_msg = await message.reply_text("⏳ Downloading...")
    try:
        await message.delete()
    except:
        pass
    
    try:
        # Download with 3-step cookie fallback
        filepath = await run_ytdl(url, audio_only)
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        # Check file size (Telegram limit is 2GB for bots)
        if filesize > 2 * 1024 * 1024 * 1024:
            os.remove(filepath)
            return await status_msg.edit_text(
                f"❌ File too large ({filesize / (1024**3):.2f} GB). "
                "Telegram bot limit is 2GB."
            )
        
        await status_msg.edit_text(f"⬆️ Uploading {filename}...")
        
        # Upload
        if audio_only or filepath.endswith(('.mp3', '.m4a', '.opus', '.ogg')):
            await message.reply_audio(
                filepath,
                caption=f"🎵 {filename}\n\nRequested by {message.from_user.mention}",
                quote=True
            )
        else:
            await message.reply_video(
                filepath,
                caption=f"🎬 {filename}\n\nRequested by {message.from_user.mention}",
                quote=True,
                supports_streaming=True
            )
        
        await status_msg.delete()
        
        # Cleanup
        try:
            os.remove(filepath)
        except:
            pass
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")
