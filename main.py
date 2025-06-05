import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update, ReplyKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]
FORBIDDEN_WORDS = ["puto", "mierda", "idiota", "concha", "porno"]
user_activity = defaultdict(int)

# === Обработка сообщений ===
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    user = update.message.from_user
    user_id = user.id
    user_activity[user_id] += 1

    if any(w in text for w in FORBIDDEN_LINKS + FORBIDDEN_WORDS):
        try:
            until = datetime.now() + timedelta(hours=24)
            await context.bot.restrict_chat_member(
                chat_id=GROUP_ID,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(
                f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas por incumplir las reglas."
            )
        except Exception as e:
            logger.warning(f"[mute error] {e}")
        return

    if text == "📜 reglas":
        await update.message.reply_text("📌 <b>Reglas del grupo:</b>\n1️⃣ Respeto\n2️⃣ Sin spam\n3️⃣ Contenido 18+ con cuidado\n🧵 ¡Gracias por colaborar!")
    elif text == "💬 escribile al admin":
        await update.message.reply_text(f"📩 <a href='tg://user?id={ADMIN_ID}'>Hacé click acá para hablar con el admin</a>")
    elif text == "🤖 sobre el bot":
        await update.message.reply_text("🤖 Soy un bot que ayuda a mantener orden y buena onda en el grupo ✨")

# === Приветствие ===
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        keyboard = [["📜 Reglas", "💬 Escribile al admin"], ["🤖 Sobre el bot"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>! Acá compartimos buena onda y respeto 🤝",
            reply_markup=reply_markup
        )

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📜 Reglas", "💬 Escribile al admin"], ["🤖 Sobre el bot"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "¡Hola! Soy el bot oficial de <b>San Juan Online 🇦🇷</b> 🤖\n¿En qué te puedo dar una mano?",
        reply_markup=reply_markup
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ Gracias por avisar. El equipo va a revisarlo 👀")

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:5]
    if not top:
        await update.message.reply_text("Todavía no hay actividad registrada.")
        return
    msg = "📊 Lxs más charlatanes del grupo:\n"
    for user_id, count in top:
        try:
            member = await context.bot.get_chat_member(GROUP_ID, user_id)
            msg += f"• {member.user.first_name}: {count} mensajes\n"
        except:
            continue
    await update.message.reply_text(msg)

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📜 Reglas del grupo</b>\n"
        "1️⃣ Respeto mutuo\n"
        "2️⃣ Sin spam ni links\n"
        "3️⃣ Contenido 18+ solo si es aceptado por la comunidad\n"
        "4️⃣ Privados con respeto\n"
        "5️⃣ Admins se reservan el derecho de moderar\n\n"
        "✅ Si colaboramos, el grupo será divertido y seguro para todes."
    )

# === Автопост в 09:00 ===
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text="☀️ ¡Buen día a todes! ¿Qué pensás del tema de hoy?\n#CharlitaDelDía"
    )

# === Обработка ошибок ===
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❗ Error: {context.error}")

# === Главная ===
def main():
    print("✅ Bot is starting...")
    defaults = Defaults(parse_mode="HTML")
    app = Application.builder().token(TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CommandHandler("rules", rules))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    app.add_error_handler(error_handler)

    app.job_queue.run_daily(daily_post, time=datetime.strptime("09:00", "%H:%M").time())

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
