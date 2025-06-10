import os
import logging
import re
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults, AIORateLimiter
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

LOG_CHAT_ID = ADMIN_ID  # ID чата для логов

user_warnings = defaultdict(int)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "").lower()

    if user_id == ADMIN_ID:
        return

    if update.message.forward_from or update.message.forward_sender_name:
        await update.message.delete()
        user_warnings[user_id] += 1

        if user_warnings[user_id] == 1:
            await update.message.reply_text(f"⚠️ @{user.username or user.first_name}, prohibido reenviar contenido.")
        elif user_warnings[user_id] >= 2:
            until = datetime.now() + timedelta(hours=24)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(f"🚫 @{user.username or user.first_name} fue silenciado 24h por reenviar contenido.")
            await context.bot.send_message(LOG_CHAT_ID, f"🔒 @{user.username or user.first_name} silenciado por reenviar.")

    if re.search(r'(?:t\.me|telegram\.me)/', text):
        await update.message.delete()
        user_warnings[user_id] += 1

        if user_warnings[user_id] == 1:
            await update.message.reply_text(f"⚠️ @{user.username or user.first_name}, no permitido enlaces externos.")
        elif user_warnings[user_id] >= 2:
            until = datetime.now() + timedelta(hours=24)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(f"🚫 @{user.username or user.first_name} silenciado 24h por enlaces.")
            await context.bot.send_message(LOG_CHAT_ID, f"🔒 @{user.username or user.first_name} silenciado por enlaces.")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>! Lee /reglas."
        )

async def reglas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reglas_text = (
        "📜 <b>Reglas del grupo:</b>\n"
        "1️⃣ Prohibido hacer spam.\n"
        "2️⃣ Nada de pornografía o pedofilia.\n"
        "3️⃣ Prohibido vender drogas.\n"
        "4️⃣ Respetá siempre a los demás."
    )
    await update.message.reply_text(reglas_text)

def main():
    defaults = Defaults(parse_mode="HTML")
    app = Application.builder().token(TOKEN).defaults(defaults).rate_limiter(AIORateLimiter()).build()

    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, handle_messages))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
