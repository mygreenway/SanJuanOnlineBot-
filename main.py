import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults, AIORateLimiter,
    CallbackQueryHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")

FORBIDDEN_WORDS = [
    "sexting", "cogiendo", "videollamada", "encuentros", "contenido", "flores",
    "nieve", "tussy", "global66", "mercado pago", "prex", "sexo"
]
SPAM_SIGNS = ["1g", "2g", "3g", "$", "precio", "t.me", "bit.ly", "🔥", "🍑", "❄️", "📞"]

user_warnings = defaultdict(int)
reply_context = {}  # admin_id -> user_id

# === Модерация сообщений ===
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "").lower()

    # Удаление пересланных сообщений и медиа
    if update.message.forward_from or update.message.forward_sender_name or update.message.forward_date:
        try:
            await update.message.delete()
            user_warnings[user_id] += 1

            if user_warnings[user_id] == 1:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ @{user.username or user.first_name}, está prohibido reenviar contenido. Próxima vez = mute."
                )
            elif user_warnings[user_id] >= 2:
                until = datetime.now() + timedelta(hours=24)
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas por reenviar contenido."
                )
        except Exception as e:
            logger.warning(f"[Forward moderation error] {e}")
        return

    # Удаление любых ссылок
    link_pattern = r"(?:https?://|www\.|t\.me/|bit\.ly/|@\w+)"
    if re.search(link_pattern, text):
        try:
            await update.message.delete()
            user_warnings[user_id] += 1

            if user_warnings[user_id] == 1:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ @{user.username or user.first_name}, los enlaces no están permitidos. Próxima vez = mute."
                )
            elif user_warnings[user_id] >= 2:
                until = datetime.now() + timedelta(hours=24)
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas por enviar enlaces nuevamente."
                )
        except Exception as e:
            logger.warning(f"[Link moderation error] {e}")
        return

    # Удаление по ключевым словам и признакам спама
    if any(w in text for w in FORBIDDEN_WORDS) and any(s in text for s in SPAM_SIGNS):
        try:
            await update.message.delete()
            user_warnings[user_id] += 1

            if user_warnings[user_id] == 1:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ @{user.username or user.first_name}, ese tipo de contenido no está permitido. Otra infracción = mute."
                )
            elif user_warnings[user_id] >= 2:
                until = datetime.now() + timedelta(hours=24)
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas por repetir contenido prohibido."
                )
        except Exception as e:
            logger.warning(f"[Spam moderation error] {e}")

def main():
    defaults = Defaults(parse_mode="HTML")
    app = Application.builder()\
        .token(TOKEN)\
        .defaults(defaults)\
        .rate_limiter(AIORateLimiter())\
        .build()

    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS, handle_messages))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
