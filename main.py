import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults, CallbackQueryHandler
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]
FORBIDDEN_WORDS = ["porno", "pedofilia", "narcotico"]
user_warnings = defaultdict(int)
reply_context = {}

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    user_id = message.from_user.id
    text = message.text.lower()

    # Удаление ссылок и предупреждение / мут
    if any(link in text for link in FORBIDDEN_LINKS):
        await message.delete()
        user_warnings[user_id] += 1

        if user_warnings[user_id] >= 2:
            until = datetime.now() + timedelta(hours=24)
            await context.bot.restrict_chat_member(
                chat_id=GROUP_ID,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=f"🚫 @{message.from_user.username or message.from_user.first_name} fue silenciado por 24 horas por spam."
            )
        else:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=f"⚠️ @{message.from_user.username or message.from_user.first_name}, no se permiten links. Un aviso más y serás silenciado."
            )
        return

    # Запрещённые слова (возможно временно убираем)
    if any(word in text for word in FORBIDDEN_WORDS):
        await message.delete()
        return

    # Ответ администратора через бота
    if update.effective_chat.id == ADMIN_ID and message.reply_to_message:
        replied_text = message.reply_to_message.text
        for user_id, name in reply_context.items():
            if name in replied_text:
                try:
                    await context.bot.send_message(chat_id=user_id, text=message.text)
                    await message.reply_text("📨 Mensaje enviado al usuario.")
                except Exception as e:
                    await message.reply_text(f"❌ No se pudo enviar el mensaje: {e}")
                break

# === Обработка кнопки "Responder" ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[1])
    user = await context.bot.get_chat_member(GROUP_ID, user_id)
    reply_context[user_id] = user.user.first_name

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"✍️ Estás en contacto con {user.user.first_name}. Escribí lo que quieras responder y yo se lo paso."
    )

# === Команда /publicidad ===
async def publicidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Escribir al admin", url=f"https://t.me/{(await context.bot.get_chat(ADMIN_ID)).username}")]
    ])
    await update.message.reply_text(
        "👋 ¡Hola! Podés escribirme si tenés ideas, propuestas, dudas o querés hacer publicidad.\n"
        "📝 Mandá tu mensaje en un solo bloque y se lo pasaré al admin.\n"
        "Gracias por comunicarte 🤝",
        reply_markup=keyboard
    )

# === Команда /rules ===
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📜 Reglas del grupo</b>\n"
        "🚫 Prohibido el spam\n"
        "🚫 Prohibido compartir contenido pornográfico o pedófilo\n"
        "🚫 Prohibido vender drogas\n"
        "💬 Publicidad solo previa aprobación\n"
        "🤝 Respetá a los demás"
    )

# === Приветствие ===
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📨 Escribir al admin", url=f"https://t.me/{(await context.bot.get_chat(ADMIN_ID)).username}")],
            [InlineKeyboardButton("📜 Reglas", callback_data="rules")],
            [InlineKeyboardButton("📢 Publicidad", callback_data=f"responder_{user.id}")]
        ])
        await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a San Juan Online 🇦🇷!\n"
            "📌 Recordá: respeto, sin spam, nada de links.\n"
            "Para ideas o publicidad podés contactarnos:",
            reply_markup=keyboard
        )

# === Главная ===
def main():
    defaults = Defaults(parse_mode="HTML")
    app = Application.builder().token(TOKEN).defaults(defaults).build()

    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("publicidad", publicidad))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="responder_.*"))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
