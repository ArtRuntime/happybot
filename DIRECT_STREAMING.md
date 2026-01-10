# Direct Streaming Configuration

Enable direct streaming from YouTube without downloading files.

## 🎯 Benefits

- ✅ **Instant playback** - No download wait
- ✅ **Save disk space** - No files stored
- ✅ **Less bandwidth** - Only streams what's needed  
- ✅ **No cleanup** - No files to delete

## ⚙️ How to Enable

Edit `.env`:

```bash
# Enable direct streaming (default: false)
ENABLE_DIRECT_STREAMING=true

# Stream quality (default: medium)
# Options: low, medium, high
STREAM_QUALITY=medium
```

## 📝 How It Works

### Before (with downloading):
```
1. User plays song
2. yt-dlp downloads entire file (200 MB)
3. File saved to disk
4. PyTgCalls streams from local file
5. File deleted after playback
⏱️ Wait time: 30-60 seconds
💾 Disk usage: 200 MB temporarily
```

### After (direct streaming):
```
1. User plays song
2. yt-dlp extracts stream URL
3. PyTgCalls streams directly from URL
⏱️ Wait time: 2-3 seconds
💾 Disk usage: 0 MB
```

## 🔧 Technical Details

- Uses `yt-dlp` to extract direct stream URLs
- PyTgCalls streams from HTTP/HTTPS URLs
- Works for YouTube, Soundcloud, and other sites
- Telegram files still use normal download (as before)

## ⚠️ Limitations

1. **Stream expires** - URL valid for ~6 hours
   - Not an issue for real-time playback
   - Preloaded songs re-fetch URL when needed

2. **Network dependent** - Requires stable connection
   - If streaming fails, falls back to download

3. **Quality selection** - Limited to available streams
   - `low`: 64-128 kbps audio
   - `medium`: 128-192 kbps audio (default)
   - `high`: 192-320 kbps audio

## 🎵 What Streams Directly

✅ **Yes** - Direct streaming:
- YouTube videos/songs
- SoundCloud tracks
- Direct MP3/MP4 URLs
- Other yt-dlp supported sites

❌ **No** - Still downloads:
- Telegram files (t.me links)
- Files from Telegram messages
- Playlists longer than 50 songs (fallback)

## 💡 Recommended Settings

### For Fast Server with Good Connection:
```bash
ENABLE_DIRECT_STREAMING=true
STREAM_QUALITY=high
```

### For Slow/Limited Connection:
```bash
ENABLE_DIRECT_STREAMING=false  # Download mode (safer)
```

### Balanced (Recommended):
```bash
ENABLE_DIRECT_STREAMING=true
STREAM_QUALITY=medium  # Best balance
```

## 🐛 Troubleshooting

### Issue: "Stream URL expired"
**Cause**: URL expired after 6 hours  
**Solution**: Bot automatically re-fetches. No action needed.

### Issue: Buffering/stuttering
**Cause**: Slow network connection  
**Solution**: 
1. Lower quality: `STREAM_QUALITY=low`
2. Or disable: `ENABLE_DIRECT_STREAMING=false`

### Issue: Stream fails randomly
**Cause**: Network instability  
**Solution**: Bot automatically falls back to download mode

## ✅ Summary

Direct streaming is **highly recommended** for:
- ✅ Servers with good network
- ✅ Bots with limited disk space
- ✅ Faster user experience

Turn it off only if you have network issues.
