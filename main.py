# -*- coding: utf-8 -*-
# San Juan Online Bot — stable build (reply-by-message, lazy bot link, inbox fix) — 2025-08-09

import os
import re
import sys
import json
import signal
import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from collections import defaultdict, OrderedDict

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LinkPreviewOptions,
    ForceReply,
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
            "message": record.getMessage(),  # безопасное имя
        }
        for key in ("event", "chat_id", "user_id", "update_id", "message_id", "warns", "reason", "detail", "trace"):
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
GROUP_ID = int(os.getenv("GROUP_ID", "0"))         # optional ограничение на один чат
BOT_LINK_ENV = os.getenv("BOT_LINK")               # опция: https://t.me/YourBot?start=contact
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")  # если есть — используем для ссылки

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
ALLOWED_FORWARD_CHATS = set()  # e.g. {-1001234567890}
EMOJI_RE = r'[\U0001F300-\U0001F6FF\U0001F900-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]'

user_warnings = defaultdict(int)

# LRU: admin_chat_message_id -> user_id
reply_map: "OrderedDict[int,int]" = OrderedDict()
REPLY_MAP_LIMIT = 1000

def reply_map_put(message_id: int, user_id: int):
    if message_id in reply_map:
        reply_map.move_to_end(message_id)
    reply_map[message_id] = user_id
    if len(reply_map) > REPLY_MAP_LIMIT:
        reply_map.popitem(last=False)

def reply_map_get(message_id: int):
    return reply_map.get(message_id)

print("✅ BOT ACTIVADO – STABLE (reply-by-message, lazy bot link, inbox fix)")

# ===================== HELPERS =====================
def is_allowed_link(text: str) -> bool:
    tl = text.lower()
    return any(allowed in tl for allowed in ALLOWED_LINKS)

async def safe_delete(msg):
    try:
        await msg.delete()
    except Exception as e:
        logger.debug("delete_skip", extra={"event": "delete_skip", "detail": repr(e)})

def safe_preview(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    t = text.replace("\n", " ")
    return (t[:limit] + "…") if len(t) > limit else t

def build_bot_link_from_username(username: str | None) -> str:
    return f"https://t.me/{username}?start=contact" if username else ""

def log_exc(event: str, err: Exception, **kw):
    logger.error(event, extra={
        "event": event,
        "detail": repr(err),
        "trace": "".join(traceback.format_exception(None, err, err.__traceback__))[:4000],
        **kw
    })

# Ленивое получение ссылки на бота с кэшем: BOT_LINK > BOT_USERNAME > get_me
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
    bot_link = await get_bot_link(context)
    extra = f"\n\n🔗 <a href='{bot_link}'>Escribir al bot</a>" if bot_link else ""
    await update.message.reply_text(
        "👋 ¡Hola! Este es el bot de <b>San Juan Online</b>.\n"
        "Escribí tu mensaje acá y se lo envío al admin. ¡Gracias!" + extra
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

# Команда в группе: кнопка на ЛС бота
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
        link_line = f"\n🔗 <b>Contacto:</b> <a href='{bot_link}'>Escribí al bot</a>" if bot_link else ""
        text = (
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>!\n\n"
            "📜 <b>Reglas rápidas:</b>\n"
            "• No spam, No porno, No drogas.\n"
            "• Sin links ni menciones a otros grupos/canales.\n"
            "• Reenvíos de canales ajenos: prohibidos.\n"
            "• Exceso de emojis: mute.\n"
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
        except Exception as e:
            logger.warning("delete_error", extra={"event": "delete_error", "chat_id": chat_id, "user_id": user_id, "detail": repr(e)})

        user_warnings[user_id] += 1
        logger.info("warn", extra={"event": "warn", "chat_id": chat_id, "user_id": user_id, "warns": user_warnings[user_id], "reason": reason})

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
        log_exc("moderation_error", e)

# ===================== GROUP MSGS ==================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if GROUP_ID and update.message.chat.id != GROUP_ID:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "")

    # не трогаем админов/создателя
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user.id)
        if chat_member.status in ("administrator", "creator"):
            return
    except Exception as e:
        logger.debug("get_chat_member_fail", extra={"event": "get_chat_member_fail", "detail": repr(e)})

    # forward check (Bot API 7.0+)
    origin = getattr(update.message, "forward_origin", None)
    is_forward = origin is not None

    if is_forward:
        src_chat = getattr(origin, "chat", None)
        src_id = getattr(src_chat, "id", None)
        source_ok = src_id in ALLOWED_FORWARD_CHATS if src_id is not None else False

        if not source_ok:
            await moderate_and_mute(update, context, user, chat_id, "reenviar mensajes (no permitido)")
            logger.info("forward_blocked", extra={"event": "forward_blocked", "chat_id": chat_id, "user_id": user.id, "reason": "not_whitelisted", "src_chat": src_id})
            return

    # ссылки/упоминания (игнорируем e-mail)
    text_lower = text.lower()
    text_sanitized = re.sub(r"\S+@\S+\.\S+", "", text_lower)

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

    # лимит эмодзи
    emoji_count = len(re.findall(EMOJI_RE, text))
    if emoji_count > 10:
        await moderate_and_mute(update, context, user, chat_id, "exceso de emojis")
        return

# ============== INBOX to ADMIN (PRIVATE) ===========
# Пересылаем ЛЮБОЕ личное сообщение админу через copy_message + безопасные id
# Если copy падает, делаем текстовый fallback
async def inbox_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return

    try:
        from_chat_id = update.effective_chat.id
        msg_id = update.message.message_id

        copied = await context.bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=from_chat_id,
            message_id=msg_id
        )
        reply_map_put(copied.message_id, user.id)

        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📨 Responder", callback_data=f"responder_{user.id}:{copied.message_id}")]]
        )
        info = await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(f"👆 Mensaje de @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n"
                  f"Respondé <b>en reply</b> a ese mensaje o tocá «Responder»."),
            reply_markup=kb
        )
        reply_map_put(info.message_id, user.id)

        await update.message.reply_text("✅ Mensaje enviado al admin.")
        logger.info("inbox", extra={"event": "inbox", "user_id": user.id})

    except Exception as e:
        # текстовый фоллбек
        try:
            text = update.message.text or "(mensaje sin texto / contenido no copiable)"
            info = await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📢 De @{user.username or user.first_name} (ID: <code>{user.id}</code>):\n\n{safe_preview(text)}"
            )
            reply_map_put(info.message_id, user.id)
            await update.message.reply_text("✅ Mensaje enviado al admin.")
            logger.warning("inbox_fallback", extra={"event": "inbox_fallback", "detail": repr(e)})
        except Exception as e2:
            log_exc("inbox_error", e2)
            await update.message.reply_text("⚠️ No pude reenviar tu mensaje. Probá de nuevo más tarde.")

# ===================== CALLBACKS ===================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("responder_"):
        try:
            payload = query.data.split("_", 1)[1]  # "<uid>:<mid>"
            uid_str, ref_mid_str = payload.split(":")
            target_id = int(uid_str)
            ref_mid = int(ref_mid_str)
        except Exception:
            target_id, ref_mid = None, None

        prompt = await query.message.reply_text(
            f"✍️ Escribí tu respuesta para <a href='tg://user?id={target_id}'>este usuario</a> "
            f"y enviála (se reenviará en su privado).",
            reply_markup=ForceReply(selective=True)
        )
        reply_map_put(prompt.message_id, target_id)
        if ref_mid:
            reply_map_put(ref_mid, target_id)
        logger.info("reply_prompt", extra={"event": "reply_prompt", "user_id": target_id})

# ===================== ADMIN REPLY =================
# Админ отвечает ТОЛЬКО по reply: адресат берётся из reply_map по message_id
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    r = update.message.reply_to_message
    if not r:
        await update.message.reply_text("ℹ️ Para responder, contestá «en reply» al mensaje del usuario o usá el botón «Responder».")
        return

    target_id = reply_map_get(r.message_id)
    if not target_id:
        await update.message.reply_text("⚠️ No encuentro destinatario para este reply. Usá el botón «Responder» debajo del mensaje del usuario.")
        return

    try:
        await context.bot.copy_message(
            chat_id=target_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        await update.message.reply_text("✅ Enviado.")
        logger.info("reply_sent", extra={"event": "reply_sent", "user_id": target_id})
    except Exception as e:
        log_exc("reply_error", e, user_id=target_id)
        await update.message.reply_text("⚠️ No pude enviar el mensaje. Probá de nuevo.")

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
    # Заполним bot_link в кэше, если вдруг ещё не был построен
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
    defaults = Defaults(
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    app = Application.builder().token(TOKEN).defaults(defaults).rate_limiter(AIORateLimiter()).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler(["contacto", "admin"], contacto))

    # Вступление в группу
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Callback «Responder»
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Порядок: сначала приватка админа (любой контент), затем приватка пользователей (любой контент)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, admin_reply))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, inbox_to_admin))

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
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        stop_signals=(signal.SIGINT, signal.SIGTERM),
        drop_pending_updates=True,
        close_loop=False
    )

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
