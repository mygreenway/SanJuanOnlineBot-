# -*- coding: utf-8 -*-
# San Juan Online Bot — stable build (2025-08-09)

import os
import re
import sys
import json
import signal
import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LinkPreviewOptions,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Defaults,
    AIORateLimiter,
    CallbackQueryHandler,
)

# ===================== LOGGING =====================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_JSON = os.getenv("LOG_JSON", "1") in ("1", "true", "True")

class JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {
            "ts": datetime.utcfromtimestamp(record.created).strftime("%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # полезные поля, если переданы через extra
        for key in ("event", "chat_id", "user_id", "update_id", "message_id", "warns", "reason"):
            if hasattr(record, key):
                d[key] = getattr(record, key)
        return json.dumps(d, ensure_ascii=False)

def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    if LOG_JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)

configure_logging()
logger = logging.getLogger("sanjuan-bot")

# ===================== ENV =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))  # опционально ограничить одним чатом

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except Exception:
    ADMIN_ID = 0

if not TOKEN or not ADMIN_ID:
    logger.error("Missing ENV: BOT_TOKEN and/or ADMIN_ID")
    # Жёсткий выход, чтобы в Render сразу было видно неверную конфигурацию
    sys.exit(1)

# ===================== SETTINGS ====================
ALLOWED_LINKS = [
    "@sanjuanonlinebot",
    "https://t.me/+pn6lcd0fv5w1ndk8",
    "https://t.me/sanjuan_online",
]
ALLOWED_LINKS = [link.lower() for link in ALLOWED_LINKS]

# Разрешённые источники пересылок (ID каналов/чатов, отрицательные для каналов)
ALLOWED_FORWARD_CHATS = set()  # пример: {-1001234567890}

# Лимит эмодзи
EMOJI_RE = r'[\U0001F300-\U0001F6FF\U0001F900-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]'

# Состояние
user_warnings = defaultdict(int)  # user_id -> warns
reply_context = {}                # ADMIN_ID -> target_user_id

print("✅ BOT ACTIVADO – STABLE (signals, errors, forward_origin, ordered handlers)")

# ===================== HELPERS =====================
def is_allowed_link(text: str) -> bool:
    tl = text.lower()
    return any(allowed in tl for allowed in ALLOWED_LINKS)

async def safe_delete(msg):
    try:
        await msg.delete()
    except Exception as e:
        logger.debug("delete_skip", extra={"event": "delete_skip", "msg": repr(e)})

def safe_preview(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    t = text.replace("\n", " ")
    return (t[:limit] + "…") if len(t) > limit else t

# ===================== COMMANDS ====================
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

# ===================== WELCOME =====================
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

# ===================== MODERATION ==================
async def moderate_and_mute(update, context, user, chat_id, reason="infracción de reglas"):
    user_id = user.id
    try:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning("delete_error", extra={"event": "delete_error", "chat_id": chat_id, "user_id": user_id, "msg": repr(e)})

        user_warnings[user_id] += 1
        logger.info(
            "warn",
            extra={"event": "warn", "chat_id": chat_id, "user_id": user_id, "warns": user_warnings[user_id], "reason": reason},
        )

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
                until_date=until,
            )
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas debido a {reason} repetido."
            )
            logger.info("mute_24h", extra={"event": "mute_24h", "chat_id": chat_id, "user_id": user_id, "reason": reason})
            await asyncio.sleep(15)
            await safe_delete(msg)
    except Exception as e:
        logger.error("moderation_error", extra={"event": "error", "msg": repr(e)})

# ===================== GROUP MSGS ==================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if GROUP_ID and update.message.chat.id != GROUP_ID:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "")

    # Лог: только семплируем в DEBUG, чтобы не засорять
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "group_msg",
            extra={
                "event": "group_msg",
                "chat_id": chat_id,
                "user_id": user.id,
                "message_id": update.message.message_id,
                "update_id": update.update_id,
            },
        )

    # Не трогаем админов/создателя
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user.id)
        if chat_member.status in ("administrator", "creator"):
            return
    except Exception as e:
        logger.debug("get_chat_member_fail", extra={"event": "get_chat_member_fail", "msg": repr(e)})

    # 1) Пересланные — Bot API 7.0: forward_origin
    origin = getattr(update.message, "forward_origin", None)
    is_forward = origin is not None

    if is_forward:
        src_chat = getattr(origin, "chat", None)
        src_id = getattr(src_chat, "id", None)
        source_ok = src_id in ALLOWED_FORWARD_CHATS if src_id is not None else False

        if not source_ok:
            await moderate_and_mute(update, context, user, chat_id, "reenviar mensajes (no permitido)")
            logger.info(
                "forward_blocked",
                extra={"event": "forward_blocked", "chat_id": chat_id, "user_id": user.id, "reason": "not_whitelisted", "src_chat": src_id},
            )
            return

    # 2) Ссылки/упоминания (игнорируем e-mail)
    text_lower = text.lower()
    text_sanitized = re.sub(r"\S+@\S+\.\S+", "", text_lower)  # убрать emails

    link_patterns = [
        r"https?://",
        r"t\.me/",
        r"telegram\.me/",
        r"t\[\.\]me",
        r"telegram\[\.\]me",
        r"(?<!\S)@\w{3,}",
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

# ============== INBOX to ADMIN (PRIVATE) ===========
async def inbox_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Личные сообщения от обычных пользователей → админу с кнопкой Responder."""
    user = update.message.from_user
    if user.id == ADMIN_ID:
        return  # админ сюда не должен попадать

    text = update.message.text or "(sin texto)"
    user_link = f"tg://user?id={user.id}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📨 Responder", callback_data=f"responder_{user.id}")]])

    logger.info("inbox", extra={"event": "inbox", "user_id": user.id})
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📢 <b>De:</b> @{user.username or user.first_name}\n\n{safe_preview(text)}\n\n{user_link}",
        reply_markup=kb,
    )
    await update.message.reply_text("✅ Mensaje enviado al admin.")

# ===================== CALLBACKS ===================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("responder_"):
        target_id = int(query.data.split("_", 1)[1])
        reply_context[ADMIN_ID] = target_id
        await query.message.reply_text(
            f"✍️ Escribí tu respuesta. Se enviará a <a href='tg://user?id={target_id}'>este usuario</a>."
        )
        logger.info("reply_select", extra={"event": "reply_select", "user_id": target_id})

# ===================== ADMIN REPLY =================
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приватные сообщения от админа — отправляются последнему выбранному адресату через кнопку Responder."""
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

    await context.bot.send_message(chat_id=target_id, text=f"📬 <b>Mensaje del admin</b>:\n\n{text}")
    await update.message.reply_text("✅ Enviado.")
    logger.info("reply_sent", extra={"event": "reply_sent", "user_id": target_id})

# ===================== ERROR HANDLER ===============
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    tb = "".join(traceback.format_exception(None, err, err.__traceback__))[:4000]
    upd_id = getattr(update, "update_id", None)
    logger.error(
        "handler_error",
        extra={"event": "error", "update_id": upd_id, "msg": repr(err)},
    )
    # Можно дополнительно слать админу в ЛС при крит. ошибках (по желанию)

def handle_asyncio_exception(loop, context):
    msg = context.get("exception") or context.get("message")
    logger.error("asyncio_error", extra={"event": "asyncio_error", "msg": repr(msg)})

# ===================== MAIN ========================
def main():
    # Глобальный обработчик исключений asyncio
    asyncio.get_event_loop().set_exception_handler(handle_asyncio_exception)

    defaults = Defaults(
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    app = Application.builder().token(TOKEN).defaults(defaults).rate_limiter(AIORateLimiter()).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(CommandHandler("help", help_command))

    # Приветствие новых участников
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Callback «Responder»
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Порядок ВАЖЕН: сначала приватка админа, потом приватка юзеров
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, admin_reply))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, inbox_to_admin))

    # Группа: обычные тексты (не команды)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_messages))

    # Глобальный обработчик ошибок PTB
    app.add_error_handler(on_error)

    logger.info("🚀 Bot is starting polling…")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        stop_signals=(signal.SIGINT, signal.SIGTERM),  # корректная остановка на Render
        drop_pending_updates=True,                     # не обрабатывать старые апдейты после рестарта
        close_loop=False
    )

if __name__ == "__main__":
    main()
