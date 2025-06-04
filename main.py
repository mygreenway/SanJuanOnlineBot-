import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, Defaults

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает! Я получил твоё сообщение.")

def main():
    app = Application.builder().token(TOKEN).defaults(Defaults(parse_mode="HTML")).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
