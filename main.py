# -*- coding: utf-8 -*-
# San Juan Online Bot — simple forward PM -> admin + welcome contact link — 2025-08-17

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
            "message": record.getMessage(),
        }
        for key in ("event", "chat_id", "user_id", "update_id", "message_id", "warns", "reason", "detail", "trace"):
            if hasattr(record, key):
                d[key] = getattr(record, key)
        return json.dumps(d, ensure_ascii=False)

def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if LOG_JSON else logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)

configure_logging()
logger = logging.getLogger("sanjuan-bot")

# ===================== ENV =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))         # optional ограничение на один чат
BOT_LINK_ENV = os.getenv("BOT_LINK")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except Exception:
    ADMIN_ID = 0

if not TOKEN or not ADMIN_ID:
    logger.error("Missing ENV: BOT_TOKEN and/or ADMIN_ID")
    sys.exit(1)

# ===================== SETTINGS ====================
ALLOWED_LINKS = [
    "@sanjuanonlinebot",
    "https://t.me/+pn6lcd0fv5w1ndk8",
    "https://t.me/sanjuan_online",
]
ALLOWED_LINKS = [link.lower() for link in ALLOWED_LINKS]
ALLOWED_FORWARD_CHATS = set()
EMOJI_RE = r'[\U0001F300-\U0001F6FF\U0001F900-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]'
user_warnings = defaultdict(int)

print("✅ BOT ACTIVADO – SIMPLE (PM forward only, welcome contact link)")

# ===================== HELPERS =====================
def is_allowed_link(text: str) -> bool:
    tl = text.lower()
    return any(allowed in tl for allowed in ALLOWED_LINKS)

async def safe_delete(msg):
    try:
        await msg.delete()
    except Exception as e:
        logger.debug("delete_skip", extra={"event": "delete_skip", "detail": repr(e)})

def build_bot_link_from_username(username: str | None) -> str:
    return f"https://t.me/{username}?start=contact" if username else ""

def log_exc(event: str, err: Exception, **kw):
    logger.error(event, extra={
        "event": event,
        "detail": repr(err),
        "trace": "".join(traceback.format_exception(None, err, err.__traceback__))[:4000],
        **kw
    })

async def get_bot_link(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    link = context.bot_data.get("bot_link")
    if link:
        return link
    if BOT_LINK_ENV:
        context.bot_data["bot_link"] = BOT_LINK_ENV
        return BOT_LINK_ENV
    if BOT_USERNAME:
        link = build_bot_link_from_username(BOT_USERNAME)
        context.bot_data["bot_link"] = link
        return link
    try:
        me = await context.bot.get_me()
        username = getattr(me, "username", None)
        if username:
            link = build_bot_link_from_username(username)
            context.bot_data["bot_link"] = link
            logger.info("bot_link_ready", extra={"event": "bot_link_ready", "detail": link})
            return link
    except Exception as e:
        logger.error("bot_link_fail", extra={"event": "error", "detail": repr(e)})
    return None

# ===================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Este es el bot de <b>San Juan Online</b>.\n\n"
        "✉️ Escribí tu mensaje acá y lo voy a reenviar al admin.\n"
        "Gracias por comunicarte 🙌"
    )

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
        "✉️ Escribí cualquier mensaje acá en privado: se reenvía al admin."
    )

async def contacto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if GROUP_ID and update.message.chat.id != GROUP_ID:
        return
    bot_link = await get_bot_link(context) or "https://t.me/"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Escribir al bot", url=bot_link)]])
    await update.message.reply_text("Para hablar con el admin, abrí el chat privado con el bot:", reply_markup=kb)

# ===================== WELCOME =====================
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        bot_link = await get_bot_link(context)
        link_line = (
            f"\n\n❓ <b>Por preguntas o propuestas contactá con el admin:</b>\n"
            f"🔗 <a href='{bot_link}'>Escribí al bot</a>"
        ) if bot_link else ""

        text = (
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>!\n\n"
            "📜 <b>Reglas rápidas:</b>\n"
            "• No spam, No porno, No drogas.\n"
            "• Sin links ni menciones a otros grupos/canales.\n"
            "• Reenvíos de canales ajenos: prohibidos.\n"
            "• Exceso de emojis: mute."
            f"{link_line}"
        )
        msg = await update.message.reply_text(text, disable_web_page_preview=True)
        await asyncio.sleep(60)
        await safe_delete(msg)

# ===================== MODERATION ==================
async def moderate_and_mute(update, context, user, chat_id, reason="infracción de reglas"):
    user_id = user.id
    try:
        try:
            await update.message.delete()
        except Exception:
            pass
        user_warnings[user_id] += 1
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
            await asyncio.sleep(15)
            await safe_delete(msg)
    except Exception as e:
        log_exc("moderation_error", e)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if GROUP_ID and update.message.chat.id != GROUP_ID:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "")

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user.id)
        if chat_member.status in ("administrator", "creator"):
            return
    except Exception:
        pass

    # блокировка ссылок/упоминаний
    text_lower = text.lower()
    text_sanitized = re.sub(r"\S+@\S+\.\S+", "", text_lower)
    link_patterns = [r"https?://", r"t\.me/", r"telegram\.me/", r"(?<!\S)@\w{3,}"]
    for pattern in link_patterns:
        if re.search(pattern, text_sanitized):
            if not is_allowed_link(text_sanitized):
                await moderate_and_mute(update, context, user, chat_id, "publicar enlaces o menciones no permitidos")
                return

    # лимит эмодзи
    emoji_count = len(re.findall(EMOJI_RE, text))
    if emoji_count > 10:
        await moderate_and_mute(update, context, user, chat_id, "exceso de emojis")
        return

# ===================== PRIVATE PM ==================
async def inbox_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return
    try:
        await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        await update.message.reply_text("✅ Mensaje enviado al admin.")
    except Exception as e:
        log_exc("inbox_error", e)
        await update.message.reply_text(
            "⚠️ No pude reenviar tu mensaje al admin.\n"
            "Posibles causas:\n"
            "• El admin aún no inició el chat con el bot (/start).\n"
            "• ADMIN_ID incorrecto."
        )

# ===================== ERROR HANDLER ===============
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    upd_id = getattr(update, "update_id", None)
    logger.error("handler_error", extra={"event": "error", "update_id": upd_id, "detail": repr(err)})

def handle_asyncio_exception(loop, context):
    msg = context.get("exception") or context.get("message")
    logger.error("asyncio_error", extra={"event": "asyncio_error", "detail": repr(msg)})

# ===================== POST INIT ===================
async def post_init(app: Application):
    try:
        if BOT_LINK_ENV:
            app.bot_data["bot_link"] = BOT_LINK_ENV
        elif BOT_USERNAME:
            app.bot_data["bot_link"] = build_bot_link_from_username(BOT_USERNAME)
        else:
            me = await app.bot.get_me()
            username = getattr(me, "username", None)
            if username:
                app.bot_data["bot_link"] = build_bot_link_from_username(username)
        logger.info("bot_link_ready", extra={"event": "bot_link_ready", "detail": app.bot_data.get("bot_link")})
    except Exception as e:
        logger.error("bot_link_fail", extra={"event": "error", "detail": repr(e)})

# ===================== MAIN ========================
def make_app() -> Application:
    defaults = Defaults(parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
    app = Application.builder().token(TOKEN).defaults(defaults).rate_limiter(AIORateLimiter()).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler(["contacto", "admin"], contacto))

    # Вступление в группу
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Приватка: пользователи → админу
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.User(ADMIN_ID) & ~filters.COMMAND, inbox_to_admin))

    # Группа: тексты
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_messages))

    # Ошибки + post_init
    app.add_error_handler(on_error)
    app.post_init = post_init
    return app

def main():
    asyncio.get_event_loop().set_exception_handler(handle_asyncio_exception)
    app = make_app()
    logger.info("🚀 Bot is starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=(signal.SIGINT, signal.SIGTERM), drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    import time
    from telegram.error import Conflict
    while True:
        try:
            main()
            break
        except Conflict:
            logger.error("conflict_retry", extra={"event": "conflict_retry", "detail": "another getUpdates is running; retry in 30s"})
            time.sleep(30)
        except Exception as e:
            logger.error("fatal_crash", extra={"event": "fatal_crash", "detail": repr(e)})
            time.sleep(15)
