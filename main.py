# San Juan Online Bot — fixed

import os
import logging
import asyncio
import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults, AIORateLimiter,
    CallbackQueryHandler
)

# --- Логи ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- ENV ---
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))  # опционально
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Разрешённые ссылки ---
ALLOWED_LINKS = [
    "@sanjuanonlinebot",
    "https://t.me/+pn6lcd0fv5w1ndk8",
    "https://t.me/sanjuan_online"
]
ALLOWED_LINKS = [link.lower() for link in ALLOWED_LINKS]

# --- Разрешённые источники пересылок (ID каналов/чатов) ---
ALLOWED_FORWARD_CHATS = set()  # например: { -1001234567890 }

# --- Глобальное состояние ---
user_warnings = defaultdict(int)
reply_context = {}  # admin_id -> target_user_id

print("✅ BOT ACTIVADO – NUEVA VERSIÓN (fix reply, rules inline, forward check)")

# --- Helpers ---
def is_allowed_link(text: str) -> bool:
    text_lower = text.lower()
    for allowed in ALLOWED_LINKS:
        if allowed in text_lower:
            return True
    return False

EMOJI_RE = r'[\U0001F300-\U0001F6FF\U0001F900-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]'

async def safe_delete(msg):
    try:
        await msg.delete()
    except Exception as e:
        logger.debug(f"Delete skipped: {e}")

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Mandá tu mensaje al admin o preguntá dudas. ¡Gracias!")

async def reglas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 <b>Reglas del grupo</b>\n"
        "• No spam, No porno, No drogas.\n"
        "• Sin links ni menciones a otros grupos/canales.\n"
        "• Respeto siempre.\n"
        "• Reenvíos de canales ajenos: prohibidos.\n"
        "• Exceso de emojis: mute.\n"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>🛟 Ayuda del Bot</b>\n\n"
        "👉 <b>/start</b> – Iniciar charla con el bot.\n"
        "📜 <b>/reglas</b> – Reglas del grupo.\n"
        "🚨 <b>/help</b> – Este mensaje.\n\n"
        "🔸 Prohibido publicar enlaces, menciones o spam.\n"
        "🔸 Para hablar con el admin, escribí acá al bot.\n"
        "<i>¡Gracias por mantener la comunidad limpia!</i>"
    )

# --- Приветствие новых участников (без кнопки, правила сразу) ---
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        text = (
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>!\n\n"
            "📜 <b>Reglas rápidas:</b>\n"
            "• No spam, No porno, No drogas.\n"
            "• Sin links ni menciones a otros grupos/canales.\n"
            "• Reenvíos de canales ajenos: prohibidos.\n"
            "• Exceso de emojis: mute.\n\n"
            "Si tenés dudas — escribí al bot. ¡Disfrutá!"
        )
        msg = await update.message.reply_text(text)
        await asyncio.sleep(60)
        await safe_delete(msg)

# --- Модерация и мут ---
async def moderate_and_mute(update, context, user, chat_id, reason="infracción de reglas"):
    user_id = user.id
    try:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"[Delete error] {e}")

        user_warnings[user_id] += 1
        logger.info(f"Warn {user_id} ({user.username}): {user_warnings[user_id]} due to {reason}")

        if user_warnings[user_id] == 1:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ @{user.username or user.first_name}, tu mensaje fue eliminado por {reason}. Próxima vez = mute 24h."
            )
            await asyncio.sleep(15)
            await safe_delete(msg)
        elif user_warnings[user_id] >= 2:
            until = datetime.now(timezone.utc) + timedelta(hours=24)
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
            await safe_delete(msg)
    except Exception as e:
        logger.warning(f"[Moderation error] {e}")

# --- Обработка обычных сообщений в группе ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Если хотим ограничить конкретным GROUP_ID (опционально)
    if GROUP_ID and update.message.chat.id != GROUP_ID:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "")

    # Админов не трогаем
    chat_member = await context.bot.get_chat_member(chat_id, user.id)
    if chat_member.status in ['administrator', 'creator']:
        return

    # 1) Пересланные сообщения — аккуратная проверка
    is_fwd = bool(
        (hasattr(update.message, "is_automatic_forward") and update.message.is_automatic_forward)
        or update.message.forward_from
        or update.message.forward_from_chat
    )
    if is_fwd:
        # Разрешим пересылки только из whitelisted источников
        source_ok = False
        if update.message.forward_from_chat:
            src_id = update.message.forward_from_chat.id
            if src_id in ALLOWED_FORWARD_CHATS:
                source_ok = True
        if not source_ok:
            await moderate_and_mute(update, context, user, chat_id, "reenviar mensajes (no permitido)")
            return

    # 2) Ссылки/упоминания
    text_lower = text.lower()

    # игнорируем e-mail, чтобы не ловить их как @mention
    text_sanitized = re.sub(r'\S+@\S+\.\S+', '', text_lower)

    link_patterns = [
        r'https?://', r't\.me/', r'telegram\.me/', r't\[\.\]me', r'telegram\[\.\]me',
        r'(?<!\S)@\w{3,}'
    ]
    for pattern in link_patterns:
        if re.search(pattern, text_sanitized):
            if not is_allowed_link(text_sanitized):
                await moderate_and_mute(update, context, user, chat_id, "publicar enlaces o menciones no permitidos")
                return

    # 3) Эмодзи лимит
    emoji_count = len(re.findall(EMOJI_RE, text))
    if emoji_count > 10:
        await moderate_and_mute(update, context, user, chat_id, "exceso de emojis")
        return

# --- Личные сообщения от пользователей → админу ---
async def inbox_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ЛС от обычных юзеров → пересылаем админу с кнопкой Responder."""
    user = update.message.from_user
    if user.id == ADMIN_ID:
        return  # этим хэндлером админа не ловим

    user_link = f"tg://user?id={user.id}"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📨 Responder", callback_data=f"responder_{user.id}")]]
    )
    text = update.message.text or "(sin texto)"
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📢 <b>De:</b> @{user.username or user.first_name}\n\n{text}\n\n{user_link}",
        reply_markup=kb
    )
    await update.message.reply_text("✅ Mensaje enviado al admin.")

# --- Ответ админа адресату после нажатия «Responder» ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("responder_"):
        target_id = int(query.data.split("_", 1)[1])
        reply_context[ADMIN_ID] = target_id
        await query.message.reply_text(
            f"✍️ Escribí tu respuesta. Se enviará a <a href='tg://user?id={target_id}'>este usuario</a>."
        )

# --- Приватные сообщения от админа с ответом ---
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    target_id = reply_context.get(ADMIN_ID)
    if not target_id:
        await update.message.reply_text("⚠️ No hay destinatario seleccionado. Tocá «Responder» debajo del mensaje.")
        return
    text = update.message.text or ""
    if not text.strip():
        await update.message.reply_text("⚠️ Mensaje vacío.")
        return

    await context.bot.send_message(chat_id=target_id, text=f"📬 <b>Mensaje del admin</b>:\n\n{text}")
    await update.message.reply_text("✅ Enviado.")

# --- main ---
def main():
    defaults = Defaults(parse_mode="HTML", disable_web_page_preview=True)
    app = Application.builder().token(TOKEN).defaults(defaults).rate_limiter(AIORateLimiter()).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(CommandHandler("help", help_command))

    # Сервис: вход в группу
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Callback: выбор адресата для ответа админом
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Приватка: сначала ловим ответы админа
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.USER(ADMIN_ID), admin_reply))

    # Приватка: входящая от обычных пользователей → админу
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.USER(ADMIN_ID), inbox_to_admin))

    # Группа: все обычные тексты (не команды)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_messages))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
