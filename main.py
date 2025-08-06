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

# --- Настройка логов ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Разрешённые ссылки ---
ALLOWED_LINKS = [
    "@sanjuanonlinebot",
    "https://t.me/+pn6lcd0fv5w1ndk8",
    "https://t.me/sanjuan_online"
]

user_warnings = defaultdict(int)
reply_context = {}

print("✅ BOT ACTIVADO – NUEVA VERSIÓN")

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Mandá tu mensaje al admin o preguntá dudas. ¡Gracias!")

async def reglas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📜 <b>Reglas:</b> No spam, No porno, No drogas, Respeto siempre.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>🛟 Ayuda del Bot:</b>\n\n"
        "👉 <b>/start</b> – Iniciar conversación con el bot.\n"
        "📜 <b>/reglas</b> – Reglas del grupo.\n"
        "🚨 <b>/help</b> – Mostrar este mensaje.\n\n"
        "🔸 Prohibido publicar enlaces, menciones o spam.\n"
        "🔸 Si deseas contactar al administrador, escribe directamente aquí al bot.\n\n"
        "<i>¡Gracias por mantener la comunidad limpia y segura!</i>"
    )

# --- Приветствие новых участников ---
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Reglas del grupo", callback_data="ver_reglas")]
        ])
        msg = await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>!\n\n"
            f"Leé las reglas para evitar problemas.",
            reply_markup=keyboard
        )
        await asyncio.sleep(60)
        await msg.delete()

# --- Модерация и мут ---
async def moderate_and_mute(update, context, user, chat_id, reason):
    user_id = user.id
    try:
        await update.message.delete()
        user_warnings[user_id] += 1

        if user_warnings[user_id] == 1:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ @{user.username or user.first_name}, tu mensaje fue eliminado por {reason}. Próxima vez = mute 24h."
            )
            await asyncio.sleep(15)
            await msg.delete()
        elif user_warnings[user_id] >= 2:
            until = datetime.now() + timedelta(hours=24)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas debido a {reason} repetido."
            )
            await asyncio.sleep(15)
            await msg.delete()
    except Exception as e:
        logger.warning(f"[Moderation error] {e}")

# --- Обработка сообщений ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "").lower()

    chat_member = await context.bot.get_chat_member(chat_id, user.id)
    if chat_member.status in ['administrator', 'creator']:
        return

    if update.message.forward_from or update.message.forward_sender_name or update.message.forward_date:
        await moderate_and_mute(update, context, user, chat_id, "reenviar mensajes")
        return

    link_patterns = [r'https?://', r't\.me/', r'telegram\.me/', r'@\w{3,}']
    for pattern in link_patterns:
        if re.search(pattern, text) and not any(allowed in text for allowed in ALLOWED_LINKS):
            await moderate_and_mute(update, context, user, chat_id, "publicar enlaces no permitidos")
            return

    emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F]', text))
    if emoji_count > 10:
        await moderate_and_mute(update, context, user, chat_id, "exceso de emojis")

# Оставшаяся часть скрипта остаётся неизменной
