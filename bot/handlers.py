# bot/handlers.py
import re
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from backend.instagram_api import (
    get_post_details_by_url,
    extract_best_video_url,
    download_video_to_memory,
    InstaApiError,
)

# Принимаем ссылки /reel/, /reels/ и /p/
INSTAGRAM_URL_RE = re.compile(
    r"(https?://(?:www\.)?instagram\.com/(?:reel|reels|p)/[A-Za-z0-9_\-]+(?:/)?(?:\?[^\s]*)?)",
    re.IGNORECASE,
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли ссылку на Instagram Reels — я скачаю видео и пришлю файл."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    m = INSTAGRAM_URL_RE.search(text)
    if not m:
        await update.message.reply_text(
            "Пришли ссылку на Reels вида https://www.instagram.com/reel/<код>/ (поддерживаются также /reels/ и /p/)"
        )
        return

    insta_url = m.group(1)

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    try:
        details = get_post_details_by_url(insta_url)
        video_url = extract_best_video_url(details)
        if not video_url:
            await update.message.reply_text(
                "Не нашёл прямую ссылку на видео. Возможно, аккаунт приватный или пост удалён."
            )
            return

        video_buf = download_video_to_memory(video_url)
        if video_buf is None:
            await update.message.reply_text(
                "Видео больше лимита Telegram для ботов. Вот ссылка на скачивание:\n" + video_url
            )
            return

        await update.message.reply_video(video=video_buf, caption="Готово ✅")

    except InstaApiError as e:
        await update.message.reply_text(f"Ошибка API: {e}")
    except Exception as e:
        await update.message.reply_text(f"Неожиданная ошибка: {e}")
