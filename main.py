import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes
from collections import defaultdict
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-1001234567890"))  # заменить на ID твоей группы

FORBIDDEN_LINKS = ["http", "https", "t.me/", "bit.ly"]
FORBIDDEN_WORDS = []  # позже добавим

user_activity = defaultdict(int)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.lower()
    user_id = msg.from_user.id
    user_activity[user_id] += 1

    if any(link in text for link in FORBIDDEN_LINKS + FORBIDDEN_WORDS):
        await msg.delete()

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(f"👋 ¡Bienvenido/a {user.first_name} a San Juan Online | Argentina!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📜 Reglas", "💬 Contactar admin"], ["🤖 Sobre el bot"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("¡Hola! Soy el bot de San Juan Online | Argentina 🤖", reply_markup=markup)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ Gracias por tu reporte. El equipo de moderación lo revisará.")

async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=GROUP_ID, text="☀️ ¡Buenos días! ¿Qué opinás del tema de hoy?
#DebateDelDía")

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:5]
    if not top_users:
        await update.message.reply_text("Aún no hay actividad registrada.")
        return
    response = "📊 Usuarios más activos:
"
    for user_id, count in top_users:
        try:
            user = await context.bot.get_chat_member(GROUP_ID, user_id)
            response += f"• {user.user.first_name}: {count} mensajes
"
        except:
            continue
    await update.message.reply_text(response)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.job_queue.run_daily(daily_post, time=datetime.strptime("09:00", "%H:%M").time())
    app.run_polling()

if __name__ == "__main__":
    main()
