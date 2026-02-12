# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import types

from bot import app, config


class Inline:
    def ikb(self, **kwargs):
        return types.InlineKeyboardButton(**kwargs)

    def ikm(self, rows):
        return types.InlineKeyboardMarkup(rows)

    def controls(
        self, chat_id: int, status: str = None, timer: str = None, autoplay: bool = False, remove: bool = False, audio_tracks: int = 0, **kwargs
    ) -> types.InlineKeyboardMarkup:
        buttons = []

        # Status row (song title/status)
        if status:
            buttons.append([self.ikb(text=status, callback_data=f"controls status {chat_id}")])
        
        # Timer/Progress bar row
        if timer:
            buttons.append([self.ikb(text=timer, callback_data=f"controls status {chat_id}")])

        # Main playback controls with replay button
        if not remove:
            buttons.append([
                self.ikb(text="▷", callback_data=f"controls resume {chat_id}"),
                self.ikb(text="II", callback_data=f"controls pause {chat_id}"),
                self.ikb(text="⥁", callback_data=f"controls replay {chat_id}"),
                self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"),
                self.ikb(text="▢", callback_data=f"controls stop {chat_id}"),
            ])
        
        # Autoplay toggle row
        autoplay_icon = "✅" if autoplay else "❌"
        autoplay_row = [self.ikb(text=f"Autoplay {autoplay_icon}", callback_data=f"controls autoplay {chat_id}")]
        
        # Add audio track selector if multiple tracks available
        if audio_tracks > 1:
            autoplay_row.append(self.ikb(text=f"🎵 Audio ({audio_tracks})", callback_data=f"audio_menu {chat_id}"))
        
        buttons.append(autoplay_row)

        return self.ikm(buttons)

    def start_key(self, lang: dict, private: bool) -> types.InlineKeyboardMarkup:
        # ... existing start_key ... (truncated for brevity in search replacement)
        if private:
            return self.ikm(
                [
                    [
                        self.ikb(
                            text=lang["add_me"],
                            url=f"https://t.me/{app.username}?startgroup=true",
                        )
                    ],
                    [self.ikb(text=lang["help"], callback_data="help")],
                    [
                        self.ikb(text=lang["support"], url=config.SUPPORT_CHAT),
                        self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL),
                    ],
                ]
            )
        else:
            return self.ikm(
                [
                    [self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL)],
                ]
            )

    def help_markup(
        self, _lang: dict, back: bool = False
    ) -> types.InlineKeyboardMarkup:
        if back:
            rows = [
                [
                    self.ikb(text=_lang["back"], callback_data="help back"),
                    self.ikb(text=_lang["close"], callback_data="help close"),
                ]
            ]
        else:
            # Music bot commands
            music_cbs = ["admins", "auth", "autoplay", "blist", "login", "ping", "play", "player", "queue", "stats", "sudo"]
            # Group utility features
            group_cbs = ["federation", "locks", "filters", "admin", "afk", "sangmata", "autoforward"]
            # Fun & tools
            fun_cbs = ["games", "memes", "extras", "ytdl", "quotly", "stickers"]
            
            all_cbs = music_cbs + group_cbs + fun_cbs
            buttons = [
                self.ikb(text=cb.capitalize().replace("_", " "), callback_data=f"help {cb}")
                for cb in all_cbs
            ]
            rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]

        return self.ikm(rows)

    def play_queued(
        self, chat_id: int, position: int, _text: str
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=_text, callback_data=f"controls force {chat_id} {position}"
                    )
                ]
            ]
        )

    def cancel_dl(self, _text: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=_text, callback_data="cancel_dl"
                    )
                ]
            ]
        )

    def queue_markup(
        self, chat_id: int, status: str, playing: bool
    ) -> types.InlineKeyboardMarkup:
        if playing:
            return self.ikm(
                [
                    [
                        self.ikb(text=status, callback_data=f"controls status {chat_id}"),
                    ],
                    [
                        self.ikb(text="‖", callback_data=f"controls pause {chat_id}"),
                        self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"),
                        self.ikb(text="▢", callback_data=f"controls stop {chat_id}"),
                    ],
                ]
            )
        else:
            return self.ikm(
                [
                    [
                        self.ikb(text=status, callback_data=f"controls status {chat_id}"),
                    ],
                    [
                        self.ikb(text="▷", callback_data=f"controls resume {chat_id}"),
                        self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"),
                        self.ikb(text="▢", callback_data=f"controls stop {chat_id}"),
                    ],
                ]
            )

    def ping_markup(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, url=config.SUPPORT_CHAT)]])

    def stats_butt(self, lang: dict) -> types.InlineKeyboardMarkup:
        rows = [
            [
                self.ikb(text=lang["group"], url=config.SUPPORT_CHAT),
                self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL),
            ],
        ]
        return self.ikm(rows)

    def settings_markup(
        self, lang: dict, admin_only: str, cmd_delete: str, language: str, chat_id: int
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(text=lang["play_mode"] + " ➜", callback_data="settings"),
                    self.ikb(text=admin_only, callback_data="settings play"),
                ],
                [
                    self.ikb(text=lang["cmd_delete"] + " ➜", callback_data="settings"),
                    self.ikb(text=cmd_delete, callback_data="settings delete"),
                ],
                [
                    self.ikb(text=lang["language"] + " ➜", callback_data="settings"),
                    self.ikb(text=language, callback_data="language"),
                ],
            ]
        )

    def lang_markup(self, current_lang: str) -> types.InlineKeyboardMarkup:
        from bot import lang as lang_mod
        langs = lang_mod.get_languages()
        
        buttons = [
            self.ikb(
                text=f"{name} ({code}) {'✔️' if code == current_lang else ''}",
                callback_data=f"lang_change {code}",
            )
            for code, name in langs.items()
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        return self.ikm(rows)

    def yt_key(self, link: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(text="❐", copy_text=link),
                    self.ikb(text="Youtube", url=link),
                ],
            ]
        )

    def autoplay_menu(self, chat_id: int, current_mode: str = None) -> types.InlineKeyboardMarkup:
        """Menu to select autoplay mode: OFF, Smart, or specific genre"""
        buttons = []
        
        # Mode selection row
        mode_row = []
        modes = [("OFF", "off"), ("Smart", "smart")]
        for label, mode in modes:
            check = "✅" if current_mode == mode else "⚪"
            mode_row.append(self.ikb(text=f"{check} {label}", callback_data=f"autoplay_set {chat_id} {mode}"))
        buttons.append(mode_row)
        
        # Genre selection (3 per row)
        genres = [
            "pop", "rock", "hiphop", "electronic", "jazz", "classical",
            "metal", "country", "rnb", "indie", "latin", "kpop",
            "lofi", "blues", "reggae", "disco", "punk",
            "ambient", "random"
        ]
        
        genre_buttons = []
        for genre in genres:
            check = "✅" if current_mode == genre else "⚪"
            genre_buttons.append(
                self.ikb(text=f"{check} {genre.title()}", callback_data=f"autoplay_set {chat_id} {genre}")
            )
        
        # Arrange in rows of 3
        for i in range(0, len(genre_buttons), 3):
            buttons.append(genre_buttons[i:i+3])
        
        # Close button
        buttons.append([self.ikb(text="❌ Close", callback_data="autoplay_close")])
        
        return self.ikm(buttons)

    def audio_track_menu(self, chat_id: int, tracks: list[dict], current_index: int = 0) -> types.InlineKeyboardMarkup:
        """Menu to select audio track from available streams"""
        buttons = []
        
        # Title row
        buttons.append([self.ikb(text="🎵 Select Audio Track", callback_data="audio_menu_info")])
        
        # Track selection buttons (2 per row)
        track_buttons = []
        for track in tracks:
            idx = track["index"]
            lang = track.get("language", "unknown")
            title = track.get("title", f"Track {idx + 1}")
            
            # Show checkmark for current track
            check = "✅" if idx == current_index else "⚪"
            label = f"{check} {title} ({lang})"
            
            track_buttons.append(
                self.ikb(text=label, callback_data=f"audio_select {chat_id} {idx}")
            )
        
        # Arrange in rows of 2
        for i in range(0, len(track_buttons), 2):
            buttons.append(track_buttons[i:i+2])
        
        # Close button
        buttons.append([self.ikb(text="❌ Close", callback_data="audio_menu_close")])
        
        return self.ikm(buttons)

