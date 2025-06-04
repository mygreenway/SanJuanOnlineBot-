import os
from datetime import datetime
from collections import defaultdict
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, filters,
    CommandHandler, ContextTypes, Defaults
)

# === Настройки ===
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-1000000000000"))  # замените на свой ID группы

FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]
FORBIDDEN_WORDS = []

user_activity = defaultdict(int)

# === Обработка сообщений ===
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.lower()
    user_id = msg.from_user.id
    user_activity[user_id] += 1

    if any(word in text for word in FORBIDDEN_LINKS + FORBIDDEN_WORDS):
        await msg.delete()

# === Приветствие ===
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>! Acá compartimos buena onda y respeto 🤝"
        )

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📜 Reglas", "💬 Escribile al admin"], ["🤖 Sobre el bot"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "¡Hola! Soy el bot oficial de <b>San Juan Online 🇦🇷</b> 🤖\n¿En qué te puedo dar una mano?",
        reply_markup=markup
    )

# === Команда /report ===
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ Gracias por avisar. El equipo va a revisarlo 👀")

# === Команда /stats ===
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:5]
    if not top_users:
        await update.message.reply_text("Todavía no hay actividad registrada.")
        return

    response = "📊 Lxs más charlatanes del grupo:\n"
    for user_id, count in top_users:
        try:
            user = await context.bot.get_chat_member(GROUP_ID, user_id)
            response += f"• {user.user.first_name}: {count} mensajes\n"
        except:
            continue
    await update.message.reply_text(response)

# === Утренний пост ===
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text="☀️ ¡Buen día a todes! ¿Qué pensás del tema de hoy?\n#CharlitaDelDía"
    )

# === Запуск ===
def main():
    defaults = Defaults(parse_mode="HTML")
    app = Application.builder().token(TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    app.job_queue.run_daily(daily_post, time=datetime.strptime("09:00", "%H:%M").time())
    print("✅ Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()
