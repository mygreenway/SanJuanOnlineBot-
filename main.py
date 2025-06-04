import os
import logging
from datetime import datetime
from collections import defaultdict

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults
)

# Включаем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

# Списки запрещённого
FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]
FORBIDDEN_WORDS = ["puto", "mierda", "idiota", "concha", "porno"]  # добавь свои

# Активность участников
user_activity = defaultdict(int)

# === Обработка сообщений ===
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    user_id = update.message.from_user.id
    user_activity[user_id] += 1

    if any(w in text for w in FORBIDDEN_LINKS + FORBIDDEN_WORDS):
        await update.message.delete()

    elif text == "📜 reglas":
        await update.message.reply_text("🧵 Estas son las reglas del grupo: respetá, no spam, +18 ✅")

    elif text == "💬 escribile al admin":
        await update.message.reply_text("📩 Podés contactarte con el admin acá: @sanjuan_admin")

    elif text == "🤖 sobre el bot":
        await update.message.reply_text("🤖 Soy un bot que ayuda a mantener orden y buena onda en el grupo ✨")

# === Приветствие новых участников ===
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>! Acá compartimos buena onda y respeto 🤝"
        )

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📜 Reglas", "💬 Escribile al admin"], ["🤖 Sobre el bot"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "¡Hola! Soy el bot oficial de <b>San Juan Online 🇦🇷</b> 🤖\n¿En qué te puedo dar una mano?",
        reply_markup=reply_markup
    )

# === Команда /report ===
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ Gracias por avisar. El equipo va a revisarlo 👀")

# === Команда /stats ===
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:5]
    if not top:
        await update.message.reply_text("Todavía no hay actividad registrada.")
        return

    msg = "📊 Lxs más charlatanes del grupo:\n"
    for user_id, count in top:
        try:
            user = await context.bot.get_chat_member(GROUP_ID, user_id)
            msg += f"• {user.user.first_name}: {count} mensajes\n"
        except:
            continue
    await update.message.reply_text(msg)

# === Автоматический пост каждый день в 09:00 ===
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text="☀️ ¡Buen día a todes! ¿Qué pensás del tema de hoy?\n#CharlitaDelDía"
    )

# === Главная функция ===
def main():
    print("✅ Bot is starting...")

    defaults = Defaults(parse_mode="HTML")
    app = Application.builder().token(TOKEN).defaults(defaults).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("stats", send_stats))

    # Сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Пост каждый день
    app.job_queue.run_daily(daily_post, time=datetime.strptime("09:00", "%H:%M").time())

    # Запуск
    app.run_polling()

if __name__ == "__main__":
    main()
