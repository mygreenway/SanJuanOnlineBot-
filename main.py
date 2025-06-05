import os
import logging
import asyncio
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

FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]
user_warnings = defaultdict(int)
reply_context = {}  # admin_id -> user_id

# Обработка сообщений в группе
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

# Приветствие
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>!\n\n"
            f"🧾 <b>Leé las reglas:</b>\n"
            f"1️⃣ Prohibido hacer spam\n"
            f"2️⃣ Nada de porno ni pedofilia\n"
            f"3️⃣ Prohibido vender drogas\n"
            f"4️⃣ Respetá siempre a los demás\n\n"
            f"📢 ¿Tenés propuestas, ideas o querés hacer publicidad?\n"
            f"Escribile al admin a través del bot 👉 <a href='https://t.me/{BOT_USERNAME}'>@{BOT_USERNAME}</a>\n\n"
            f"🙌 ¡Gracias por sumarte con buena onda!"
        )

# Старт в личке
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        await update.message.reply_text(
            "👋 Hola! Escribí tu propuesta de publicidad en un solo mensaje y la enviaré al admin."
        )
    else:
        await update.message.reply_text(
            "👋 ¡Buenas! Soy el bot oficial de San Juan Online 🇦🇷. Estoy para mantener el orden del grupo."
        )

# Получение предложения в личке
async def publicidad_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return

    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_link = f"tg://user?id={user.id}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Responder", callback_data=f"responder_{user.id}")]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📢 Nueva propuesta de publicidad del usuario {username}:\n"
            f"{update.message.text}\n\n"
            f"👉 Contactar: {user_link}"
        ),
        reply_markup=keyboard
    )
    await update.message.reply_text("✅ Tu propuesta fue enviada al administrador. ¡Gracias!")

# Обработка кнопки "Responder"
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("responder_"):
        return

    user_id = int(query.data.split("_")[1])
    reply_context[query.from_user.id] = user_id
    await query.message.reply_text("✍️ Ahora estás respondiendo a ese usuario. Escribí tus mensajes y los enviaré automáticamente.")

# Админ отвечает (автоматически, если в контексте)
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_ID:
        return

    admin_id = update.message.from_user.id
    target_id = reply_context.get(admin_id)
    if not target_id:
        return

    try:
        await context.bot.send_message(chat_id=target_id, text=update.message.text)
        await update.message.reply_text("✅ Respuesta enviada al usuario.")
    except Exception as e:
        await update.message.reply_text("❌ No se pudo enviar la respuesta.")
        logger.error(f"Error al responder: {e}")

# /reglas
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

# Ошибки
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

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, publicidad_chat))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, handle_messages))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, admin_reply))

    app.add_error_handler(error_handler)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
