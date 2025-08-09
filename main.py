# -*- coding: utf-8 -*-
# San Juan Online Bot — stable build (2025-08-09)

import os
import logging
import asyncio
import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from telegram import (
    Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton,
    LinkPreviewOptions
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults, AIORateLimiter,
    CallbackQueryHandler
)

# ---------------------- LOGGING ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sanjuan-bot")

# ---------------------- ENV -------------------------
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))      # опционально ограничить одним чатом
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not TOKEN or not ADMIN_ID:
    raise RuntimeError("ENV required: BOT_TOKEN, ADMIN_ID. Optional: GROUP_ID")

# ---------------------- SETTINGS --------------------
ALLOWED_LINKS = [
    "@sanjuanonlinebot",
    "https://t.me/+pn6lcd0fv5w1ndk8",
    "https://t.me/sanjuan_online"
]
ALLOWED_LINKS = [link.lower() for link in ALLOWED_LINKS]

# Разрешённые источники пересылок (ID каналов/чатов, отрицательные для каналов)
ALLOWED_FORWARD_CHATS = set()  # пример: {-1001234567890}

# State
user_warnings = defaultdict(int)      # user_id -> warns
reply_context = {}                    # ADMIN_ID -> target_user_id

# Расширенный диапазон эмодзи
EMOJI_RE = r'[\U0001F300-\U0001F6FF\U0001F900-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]'

print("✅ BOT ACTIVADO – NUEVA VERSIÓN (fix reply, rules inline, forward check)")

# ---------------------- HELPERS ---------------------
def is_allowed_link(text: str) -> bool:
    text_lower = text.lower()
    for allowed in ALLOWED_LINKS:
        if allowed in text_lower:
            return True
    return False

async def safe_delete(msg):
    try:
        await msg.delete()
    except Exception as e:
        logger.debug(f"Delete skipped: {e}")

# ---------------------- COMMANDS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Mandá tu mensaje al admin o preguntá dudas. ¡Gracias!")

async def reglas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 <b>Reglas del grupo</b>\n"
        "• No spam, No porno, No drogas.\n"
        "• Sin links ni menciones a otros grupos/canales.\n"
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

# ---------------------- WELCOME ---------------------
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

# ---------------------- MODERATION ------------------
async def moderate_and_mute(update, context, user, chat_id, reason="infracción de reglas"):
    user_id = user.id
    try:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"[Delete error] {e}")

        user_warnings[user_id] += 1
        logger.info(f"[WARN] user={user_id} @{user.username} warns={user_warnings[user_id]} reason={reason}")

        if user_warnings[user_id] == 1:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ @{user.username or user.first_name}, tu mensaje fue eliminado por {reason}. Próxima vez = mute 24h."
            )
            await asyncio.sleep(15)
            await safe_delete(msg)
        else:
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

# ---------------------- GROUP MSGS ------------------
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if GROUP_ID and update.message.chat.id != GROUP_ID:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "")
    logger.info(f"[GROUP MSG] chat={chat_id} from={user.id} text_len={len(text)}")

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user.id)
        if chat_member.status in ['administrator', 'creator']:
            return
    except Exception as e:
        logger.debug(f"get_chat_member fail: {e}")

    # 1) Пересланные — аккуратно
    is_auto_fwd = bool(getattr(update.message, "is_automatic_forward", False))
    is_fwd_user = bool(update.message.forward_from)
    is_fwd_chat = bool(update.message.forward_from_chat)
    is_forward = is_auto_fwd or is_fwd_user or is_fwd_chat

    if is_forward:
        source_ok = False
        if update.message.forward_from_chat:
            src_id = update.message.forward_from_chat.id
            if src_id in ALLOWED_FORWARD_CHATS:
                source_ok = True
        if not source_ok:
            await moderate_and_mute(update, context, user, chat_id, "reenviar mensajes (no permitido)")
            return

    # 2) Ссылки/упоминания (с игнором email)
    text_lower = text.lower()
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

    # 3) Эмодзи-лимит
    emoji_count = len(re.findall(EMOJI_RE, text))
    if emoji_count > 10:
        await moderate_and_mute(update, context, user, chat_id, "exceso de emojis")
        return

# ---------------------- INBOX to ADMIN ---------------
async def inbox_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Личные сообщения от обычных юзеров → пересылаем админу с кнопкой Responder."""
    user = update.message.from_user
    if user.id == ADMIN_ID:
        return  # админ в этом хэндлере не нужен

    text = update.message.text or "(sin texto)"
    user_link = f"tg://user?id={user.id}"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📨 Responder", callback_data=f"responder_{user.id}")]]
    )

    logger.info(f"[INBOX] from_user={user.id} @{user.username} -> ADMIN {ADMIN_ID}")
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📢 <b>De:</b> @{user.username or user.first_name}\n\n{text}\n\n{user_link}",
        reply_markup=kb
    )
    await update.message.reply_text("✅ Mensaje enviado al admin.")

# ---------------------- CALLBACKS --------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("responder_"):
        target_id = int(query.data.split("_", 1)[1])
        reply_context[ADMIN_ID] = target_id
        await query.message.reply_text(
            f"✍️ Escribí tu respuesta. Se enviará a <a href='tg://user?id={target_id}'>este usuario</a>."
        )

# ---------------------- ADMIN REPLY ------------------
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приватные сообщения от админа — отправляются последнему выбранному адресату."""
    if update.effective_user.id != ADMIN_ID:
        return

    target_id = reply_context.get(ADMIN_ID)
    if not target_id:
        await update.message.reply_text("⚠️ No hay destinatario seleccionado. Tocá «Responder» debajo del mensaje.")
        return

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("⚠️ Mensaje vacío.")
        return

    logger.info(f"[REPLY] admin -> user_id={target_id}")
    await context.bot.send_message(chat_id=target_id, text=f"📬 <b>Mensaje del admin</b>:\n\n{text}")
    await update.message.reply_text("✅ Enviado.")

# ---------------------- MAIN ------------------------
def main():
    defaults = Defaults(
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True)  # вместо deprecated disable_web_page_preview
    )
    app = Application.builder().token(TOKEN).defaults(defaults).rate_limiter(AIORateLimiter()).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(CommandHandler("help", help_command))

    # Вступление в группу
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Callback «Responder»
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Порядок важен: сначала ловим приватные ответы админа, потом — входящие от юзеров
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, admin_reply))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, inbox_to_admin))

    # Группа: сообщения (не команды)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_messages))

    logger.info("🚀 Bot is starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
