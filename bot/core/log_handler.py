import asyncio
import logging
from html import escape

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.queue = asyncio.Queue()
        self.worker_task = None
        self.setFormatter(logging.Formatter("[%(name)s]: %(message)s"))

    def emit(self, record):
        """
        Push the formatted log record to the asyncio queue.
        This is a synchronous method calling thread-safe async queue methods.
        """
        # Exclude noisy networking libraries to prevent recursive spam
        noisy_loggers = [
            "pyrogram.connection",
            "pyrogram.session",
            "pyrogram.client",
            "ntgcalls",
            "httpx",
            "websockets",
            "httpcore"
        ]
        for noisy in noisy_loggers:
            if record.name.startswith(noisy):
                return

        try:
            msg = self.format(record)
            
            # Use put_nowait instead of blocking or thread-safe if it's running in the same thread.
            # Let's handle it safely depending on the current event loop context.
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.queue.put_nowait, (record.levelname, msg))
            except RuntimeError:
                pass # No running loop
                
        except Exception:
            self.handleError(record)

    async def _worker(self):
        """
        Background task to process logs from the queue and send them to Telegram.
        """
        while True:
            try:
                levelname, msg = await self.queue.get()
                
                # Truncate if it's too long for a single telegram message (4096 is max, code blocks take space)
                safe_msg = escape(msg)
                
                if len(safe_msg) > 3900:
                    safe_msg = safe_msg[:3900] + "... [truncated]"

                # Format the error message
                emoji = "🚨" if levelname in ["ERROR", "CRITICAL"] else "⚠️"
                text = f"{emoji} <b>{levelname} Log Tracker</b>\n\n<code>{safe_msg}</code>"
                
                # Make sure LOGGER_ID config exists and bot is ready
                if getattr(self.bot, "logger", None):
                    try:
                        await self.bot.send_message(self.bot.logger, text)
                    except Exception as e:
                        # Fallback to local printing if telegram fails
                        print(f"Failed to send log to Telegram: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker Error in TelegramLogHandler: {e}")
            finally:
                self.queue.task_done()
                # Adding small sleep to prevent flood limits if bulk errors occur
                await asyncio.sleep(1)

    def start_worker(self):
        """
        Start the background worker. Normally called during the bot's boot process.
        """
        loop = asyncio.get_running_loop()
        self.worker_task = loop.create_task(self._worker())

    async def stop_worker(self):
        """
        Stop the background worker cleanly.
        """
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
