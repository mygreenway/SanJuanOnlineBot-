import os
import logging
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

FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]

user_warnings = defaultdict(int)

# Обработка сообщений
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    user = update.message.from_user
    user_id = user.id

    if any(link in text for link in FORBIDDEN_LINKS):
        try:
            await update.message.delete()
            user_warnings[user_id] += 1
            if user_warnings[user_id] == 1:
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=f"⚠️ Che @{user.username or user.first_name}, no podés mandar links en el grupo. Próxima vez, mute por 24 horas."
                )
            elif user_warnings[user_id] > 1:
                until = datetime.now() + timedelta(hours=24)
                await context.bot.restrict_chat_member(
                    chat_id=GROUP_ID,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until
                )
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=f"🚫 @{user.username or user.first_name} silenciado por 24 horas por insistir con links."
                )
        except Exception as e:
            logger.warning(f"Error: {e}")

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Buenas! Soy el bot oficial de San Juan Online 🇦🇷. Estoy para mantener el orden del grupo."
    )

async def reglas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reglas_text = (
        "📜 <b>Reglas del grupo:</b>\n"
        "1️⃣ Prohibido hacer spam.\n"
        "2️⃣ Prohibido compartir pornografía y pedofilia.\n"
        "3️⃣ Prohibido vender drogas.\n"
        "4️⃣ Respetá siempre a los demás, cero agresión ni insultos.\n\n"
        "Gracias por respetar las reglas 👌"
    )
    await update.message.reply_text(reglas_text)

async def publicidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📩 Mandá tu propuesta de publicidad en un solo mensaje acá. El admin la revisará y se comunicará con vos si le interesa."
    )
    # Уведомление админу
    if update.message.reply_to_message is None:
        proposal = update.message.text.replace('/publicidad', '').strip()
        if proposal:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📢 Nueva propuesta de publicidad del usuario @{update.message.from_user.username or update.message.from_user.first_name}:\n{proposal}"
            )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❗ Error: {context.error}")

# Главная

def main():
    defaults = Defaults(parse_mode="HTML")

    app = Application.builder()\
        .token(TOKEN)\
        .defaults(defaults)\
        .rate_limiter(AIORateLimiter())\
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(CommandHandler("publicidad", publicidad))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
