# bot/main.py
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.request import HTTPXRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import cmd_start, handle_text


def main():
    # Грузим .env из КОРНЯ проекта (на уровень выше папки bot/)
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    # Бóльшие таймауты — реже спорадические TimedOut при отправке больших видео
    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=120,
        write_timeout=120,
        pool_timeout=30,
    )

    app = Application.builder().token(token).request(request).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is running… Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
