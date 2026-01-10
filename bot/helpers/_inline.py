# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import types

from bot import app, config, lang


class Inline:
    def __init__(self):
        self.ikm = types.InlineKeyboardMarkup
        self.ikb = types.InlineKeyboardButton

    def cancel_dl(self, text) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, callback_data=f"cancel_dl")]])

    def controls(
        self,
        chat_id: int,
        status: str = None,
        timer: str = None,
        remove: bool = False,
        autoplay: bool | str = False,
    ) -> types.InlineKeyboardMarkup:
        keyboard = []
        if status:
            keyboard.append(
                [self.ikb(text=status, callback_data=f"controls status {chat_id}")]
            )
        elif timer:
            keyboard.append(
                [self.ikb(text=timer, callback_data=f"controls status {chat_id}")]
            )

        if not remove:
            # Playback controls row
            keyboard.append(
                [
                    self.ikb(text="▷", callback_data=f"controls resume {chat_id}"),
                    self.ikb(text="II", callback_data=f"controls pause {chat_id}"),
                    self.ikb(text="⥁", callback_data=f"controls replay {chat_id}"),
                    self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"),
                    self.ikb(text="▢", callback_data=f"controls stop {chat_id}"),
                ]
            )
            # Autoplay toggle button (✅ = enabled, ❌ = disabled)
            autoplay_icon = "✅" if autoplay else "❌"
            autoplay_label = f"Autoplay {autoplay_icon}"
            keyboard.append(
                [self.ikb(text=autoplay_label, callback_data=f"controls autoplay {chat_id}")]
            )
        return self.ikm(keyboard)

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
            cbs = ["admins", "auth", "autoplay", "anime", "blist", "ping", "play", "queue", "stats", "sudo"]
            buttons = [
                self.ikb(text=cb.capitalize(), callback_data=f"help {cb}")
                for cb in cbs
            ]
            rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]

        return self.ikm(rows)

    def lang_markup(self, _lang: str) -> types.InlineKeyboardMarkup:
        langs = lang.get_languages()

        buttons = [
            self.ikb(
                text=f"{name} ({code}) {'✔️' if code == _lang else ''}",
                callback_data=f"lang_change {code}",
            )
            for code, name in langs.items()
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        return self.ikm(rows)

    def ping_markup(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, url=config.SUPPORT_CHAT)]])

    def play_queued(
        self, chat_id: int, item_id: str, _text: str
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=_text, callback_data=f"controls force {chat_id} {item_id}"
                    )
                ]
            ]
        )

    def queue_markup(
        self, chat_id: int, _text: str, playing: bool
    ) -> types.InlineKeyboardMarkup:
        _action = "pause" if playing else "resume"
        return self.ikm(
            [[self.ikb(text=_text, callback_data=f"controls {_action} {chat_id} q")]]
        )

    def settings_markup(
        self, lang: dict, admin_only: bool, cmd_delete: bool, language: str, chat_id: int
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=lang["play_mode"] + " ➜",
                        callback_data="settings",
                    ),
                    self.ikb(text=admin_only, callback_data="settings play"),
                ],
                [
                    self.ikb(
                        text=lang["cmd_delete"] + " ➜",
                        callback_data="settings",
                    ),
                    self.ikb(text=cmd_delete, callback_data="settings delete"),
                ],
                [
                    self.ikb(
                        text=lang["language"] + " ➜",
                        callback_data="settings",
                    ),
                    self.ikb(text=lang_codes[language], callback_data="language"),
                ],
            ]
        )

    def start_key(
        self, lang: dict, private: bool = False
    ) -> types.InlineKeyboardMarkup:
        rows = [
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

    def anime_search_results(self, results: list, chat_id: int, page: int = 0) -> types.InlineKeyboardMarkup:
        """Display anime search results with pagination."""
        buttons = []
        # Show 5 results per page
        start = page * 5
        end = min(start + 5, len(results))
        
        for i in range(start, end):
            anime = results[i]
            title = anime.get("title", "Unknown")
            buttons.append([
                self.ikb(text=f"📺 {title[:40]}", callback_data=f"anime_sel {chat_id} {i}")
            ])
        
        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(self.ikb(text="◀️ Prev", callback_data=f"anime_pg {chat_id} {page-1}"))
        if end < len(results):
            nav_row.append(self.ikb(text="Next ▶️", callback_data=f"anime_pg {chat_id} {page+1}"))
        
        if nav_row:
            buttons.append(nav_row)
        
        buttons.append([self.ikb(text="❌ Close", callback_data="anime_close")])
        
        return self.ikm(buttons)

    def anime_episode_selector(
        self, 
        anime_id: str, 
        episodes: list, 
        current_page: int = 0
    ) -> types.InlineKeyboardMarkup:
        """Display episode selection with pagination."""
        buttons = []
        episodes_per_page = 10
        start = current_page * episodes_per_page
        end = min(start + episodes_per_page, len(episodes))
        
        # Episode buttons (2 per row)
        ep_buttons = []
        for ep in episodes[start:end]:
            ep_no = ep.get("episode_no", "?")
            ep_id = ep.get("id", "")
            data_id = ep.get("data_id", "")
            ep_buttons.append(
                self.ikb(text=f"Ep {ep_no}", callback_data=f"anime_ep {anime_id} {data_id}")
            )
        
        # Arrange episode buttons in rows of 5
        for i in range(0, len(ep_buttons), 5):
            buttons.append(ep_buttons[i:i+5])
        
        # Pagination
        nav_row = []
        if current_page > 0:
            nav_row.append(self.ikb(text="◀️ Prev", callback_data=f"anime_ep_page {anime_id} {current_page-1}"))
        if end < len(episodes):
            nav_row.append(self.ikb(text="Next ▶️", callback_data=f"anime_ep_page {anime_id} {current_page+1}"))
        
        if nav_row:
            buttons.append(nav_row)
        
        buttons.append([
            self.ikb(text="🔙 Back", callback_data=f"anime_select {anime_id}"),
            self.ikb(text="❌ Close", callback_data="anime_close")
        ])
        
        return self.ikm(buttons)

    def anime_controls(
        self,
        chat_id: int,
        anime_id: str,
        episode_id: str,
        server: str = "hd-1",
        stream_type: str = "sub",
        status: str = None
    ) -> types.InlineKeyboardMarkup:
        """Display anime playback controls with episode/server/type selectors."""
        keyboard = []
        
        # Status bar
        if status:
            keyboard.append([
                self.ikb(text=status, callback_data=f"anime_status {chat_id}")
            ])
        
        # Main playback controls
        keyboard.append([
            self.ikb(text="▷", callback_data=f"anime_resume {chat_id}"),
            self.ikb(text="II", callback_data=f"anime_pause {chat_id}"),
            self.ikb(text="‣‣I", callback_data=f"anime_skip {chat_id}"),
            self.ikb(text="▢", callback_data=f"anime_stop {chat_id}"),
        ])
        
        # Episode/Server/Type selectors
        keyboard.append([
            self.ikb(text="📺 Episodes", callback_data=f"anime_ep_list {anime_id}"),
            self.ikb(text=f"🌐 {server.upper()}", callback_data=f"anime_server {anime_id} {episode_id}"),
            self.ikb(text=f"🗣 {stream_type.upper()}", callback_data=f"anime_type {anime_id} {episode_id} {server}")
        ])
        
        return self.ikm(keyboard)

    def anime_server_selector(
        self,
        anime_id: str,
        episode_id: str,
        servers: list,
        current_type: str = "sub"
    ) -> types.InlineKeyboardMarkup:
        """Display available servers."""
        buttons = []
        
        # Group servers by type (sub/dub)
        sub_servers = [s for s in servers if s.get("type") == "sub"]
        dub_servers = [s for s in servers if s.get("type") == "dub"]
        
        target_servers = sub_servers if current_type == "sub" else dub_servers
        
        # Server buttons
        for server in target_servers[:6]:  # Show max 6 servers
            server_name = server.get("server_name", "HD-1")
            buttons.append([
                self.ikb(
                    text=f"🌐 {server_name}",
                    callback_data=f"anime_use_server {anime_id} {episode_id} {server_name} {current_type}"
                )
            ])
        
        buttons.append([
            self.ikb(text="🔙 Back", callback_data=f"anime_ep {anime_id} {episode_id}"),
            self.ikb(text="❌ Close", callback_data="anime_close")
        ])
        
        return self.ikm(buttons)
