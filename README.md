---
title: HappyBot - Telegram Music & Anime Bot
emoji: 🎵
colorFrom: pink
colorTo: purple
sdk: docker
pinned: false
license: mit
short_description: Advanced Telegram bot for music streaming
thumbnail: >-
  https://cdn-uploads.huggingface.co/production/uploads/68d1c65f0c37d916b2989027/US350-3RWQuWZ_ODPGwjJ.png
---

# 🎵 HappyBot - Advanced Telegram Music & Anime Bot

A powerful, feature-rich Telegram bot for streaming music, videos, and anime in voice chats. Built with Python, Pyrogram, and PyTgCalls.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://telegram.org/)

## ✨ Features

### 🎶 Music Streaming
- **YouTube Integration**: Stream music/videos directly from YouTube
- **Smart Search**: Intelligent search with support for queries and direct URLs
- **Playlist Support**: Queue entire YouTube playlists
- **High Quality**: Up to 720p video and high-quality audio streaming
- **Live Controls**: Play, pause, skip, stop, and replay functionality

### 🤖 AI-Powered Autoplay
- **TF-IDF Recommendations**: Smart song suggestions based on listening history
- **Genre Detection**: Automatic genre, artist, and language detection
- **Personalized**: Learns from your music preferences
- **YouTube-Only**: Autoplay works only for YouTube sources (search & URLs)

### 📺 Anime Streaming
- **Direct Streaming**: Watch anime directly in Telegram voice chats
- **Multiple Servers**: Choose from different streaming servers (HD-1, HD-2, etc.)
- **Sub/Dub Support**: Toggle between subtitled and dubbed versions
- **Episode Selection**: Easy navigation through episodes
- **Auto-Play Movies**: Single-episode anime starts automatically

### 📁 Telegram Files
- **File Support**: Play audio/video files uploaded to Telegram
- **Auto-Download**: Automatically downloads and streams Telegram files
- **Progress Tracking**: Real-time download progress indicators

### 👥 Multi-Userbot Support
- **Dynamic Sessions**: Hot-reload userbot sessions without restart
- **Session Management**: Add/remove userbots on-the-fly
- **MongoDB Storage**: Sessions stored securely in database
- **Auto-Migration**: Automatic migration from env-based sessions

### 🎛️ Advanced Controls
- **Inline Keyboards**: Beautiful interactive controls
- **Queue Management**: View and manage playback queue
- **Seek Support**: Jump to specific timestamps
- **Autoplay Toggle**: Enable/disable autoplay per chat
- **Admin Controls**: Restrict playback to admins when needed

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- MongoDB database
- Telegram Bot Token ([BotFather](https://t.me/BotFather))
- Telegram API ID & Hash ([my.telegram.org](https://my.telegram.org))

### Installation

1. **Clone the repository**:
```bash
git clone https://huggingface.co/spaces/alex5402/happybot
cd happybot
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure environment**:
```bash
cp sample.env .env
# Edit .env with your credentials
```

4. **Required Environment Variables**:
```env
BOT_TOKEN=your_bot_token
API_ID=your_api_id
API_HASH=your_api_hash
MONGO_DB_URI=mongodb://localhost:27017
OWNER_ID=your_telegram_user_id
```

5. **Run the bot**:
```bash
python -m bot
```

### Docker Deployment

```bash
docker build -t happybot .
docker run -d --env-file .env happybot
```

## 📖 Usage

### Basic Commands

- `/start` - Start the bot
- `/help` - Show help menu
- `/play <query>` - Play audio from YouTube (search or URL)
- `/vplay <query>` - Play video from YouTube (search or URL)
- `/anime <query>` - Search and stream anime
- `/stop` - Stop playback and clear queue
- `/pause` - Pause playback
- `/resume` - Resume playback
- `/skip` - Skip to next track
- `/queue` - Show queued tracks
- `/seek <seconds>` - Seek forward
- `/seekback <seconds>` - Seek backward
- `/autoplay` - Toggle smart autoplay
- `/ping` - Check bot status
- `/stats` - Show statistics

### Admin/Sudo Commands

- `/addsession <string>` - Add userbot session
- `/rmsession <name>` - Remove userbot session
- `/sessions` - List active sessions

### Inline Controls

Every playback includes interactive buttons:
- ⏯️ Pause/Resume
- ⏭️ Skip
- 🔁 Replay
- ⏹️ Stop
- 🌐 Server (anime only)
- 🗣️ Sub/Dub (anime only)

## 🛠️ Technology Stack

- **[Pyrogram](https://docs.pyrogram.org/)**: Telegram MTProto API framework
- **[PyTgCalls](https://github.com/pytgcalls/pytgcalls)**: Voice chat streaming
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**: YouTube video extraction
- **[MongoDB](https://www.mongodb.com/)**: Database for sessions and cache
- **[FastAPI](https://fastapi.tiangolo.com/)**: Web server for health checks
- **[scikit-learn](https://scikit-learn.org/)**: ML-powered recommendations

## 🔧 Advanced Features

### Recommendation Engine
- Uses TF-IDF vectorization on song metadata
- Trains on user listening history (5+ plays)
- Fallback to genre-based recommendations
- Supports multiple languages and genres

### Anime API Integration
- Custom anime API wrapper
- Support for multiple CDN providers
- Automatic header injection for geo-restrictions
- Fallback to download for blocked streams

### Smart Caching
- Episode data cached per chat
- Reduced API calls
- Short callback data (under 64 bytes)
- Indexed storage system

## 📊 Configuration

### Optional Features
```env
# Autoplay settings
AUTOPLAY_MODE=smart  # smart|random|off

# YouTube settings
YTDLP_VERBOSE=false
PLAYLIST_LIMIT=25

# Anime API
ANIME_API_URL=https://anime-api.example.com

# Queue limits
QUEUE_LIMIT=50
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [PyTgCalls](https://github.com/pytgcalls/pytgcalls) for voice chat support
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube extraction
- Anime API providers for streaming support

## 📧 Support

For support, join our [Telegram Support Group](https://t.me/your_support_group) or open an issue.

---

**Made with ❤️ by [alex5402](https://github.com/alex5402)**
