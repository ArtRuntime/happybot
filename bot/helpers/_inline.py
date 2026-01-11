# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot


from pyrogram import types

from bot import config


class Inline:
    def ikb(self, **kwargs):
        return types.InlineKeyboardButton(**kwargs)

    def ikm(self, rows):
        return types.InlineKeyboardMarkup(rows)

    def controls(
        self, chat_id: int, status: str = None, autoplay: bool = False
    ) -> types.InlineKeyboardMarkup:
        buttons = []
        btns = []

        # Status row
        if status:
            btns.append(self.ikb(text=status, callback_data=f"controls status {chat_id}"))

        # Main playback controls
        btns.append(self.ikb(text="‖", callback_data=f"controls pause {chat_id}"))
        btns.append(self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"))
        btns.append(self.ikb(text="▢", callback_data=f"controls stop {chat_id}"))

        # Autoplay toggle
        autoplay_symbol = "∞" if autoplay else "∞"
        btns.append(self.ikb(text=autoplay_symbol, callback_data=f"controls autoplay {chat_id}"))

        buttons.append(btns)

        return self.ikm(buttons)

    def start_key(self, lang: dict, private: bool) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL)],
            ]
            if not private
            else [
                [
                    self.ikb(text=lang["help"], url=f"https://t.me/{config.BOT_USERNAME}?start=help"),
                    self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL),
                ],
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
            cbs = ["admins", "auth", "autoplay", "blist", "ping", "play", "player", "queue", "stats", "sudo"]
            buttons = [
                self.ikb(text=cb.capitalize(), callback_data=f"help {cb}")
                for cb in cbs
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

    def stats_butt(self, lang: dict) -> types.InlineKeyboardMarkup:
        rows = [
            [
                self.ikb(text=lang["group"], url=config.SUPPORT_CHAT),
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
