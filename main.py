import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, Defaults, AIORateLimiter,
    CallbackQueryHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")

ALLOWED_LINKS = ["@sanjuanonlinebot", "https://t.me/+pn6lcd0fv5w1ndk8"]

user_warnings = defaultdict(int)
reply_context = {}

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat.id
    text = (update.message.text or update.message.caption or "").lower()

    if update.message.forward_from or update.message.forward_sender_name or update.message.forward_date:
        await moderate_and_mute(update, context, user, chat_id)
        return

    if re.search(r'https?://', text):
        if not any(link in text for link in ALLOWED_LINKS):
            await moderate_and_mute(update, context, user, chat_id)
            return

    if re.search(r'@\w{3,}', text):
        if not any(link in text for link in ALLOWED_LINKS):
            await moderate_and_mute(update, context, user, chat_id)
            return

    if re.search(r'\$\d{3,}', text):  # например: $5000
        if re.search(r'(gana|dinero|invierte|enlace|haz clic|gratis|registrate|promo)', text):
            await moderate_and_mute(update, context, user, chat_id)
            return

async def moderate_and_mute(update, context, user, chat_id):
    user_id = user.id
    try:
        await update.message.delete()
        user_warnings[user_id] += 1

        if user_warnings[user_id] == 1:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ @{user.username or user.first_name}, está prohibido hacer spam. Próxima vez = mute."
            )
            await asyncio.sleep(15)
            await msg.delete()
        elif user_warnings[user_id] >= 2:
            until = datetime.now() + timedelta(hours=24)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚫 @{user.username or user.first_name} fue silenciado por 24 horas por spam."
            )
            await asyncio.sleep(15)
            await msg.delete()
    except Exception as e:
        logger.warning(f"[Moderation error] {e}")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        msg = await update.message.reply_text(
            f"👋 ¡Bienvenidx {user.first_name} a <b>San Juan Online 🇦🇷</b>!\n\n"
            f"🧾 <b>Leé las reglas:</b>\n"
            f"1️⃣ Prohibido hacer spam\n"
            f"2️⃣ Nada de porno ni pedofilia\n"
            f"3️⃣ Prohibido vender drogas\n"
            f"4️⃣ Respetá siempre a los demás\n\n"
            f"📢 ¿Tenés propuestas, ideas o querés hacer publicidad?\n"
            f"Escribile al admin a través del bot 👉 @SanJuanOnlineBot\n\n"
            f"🙌 ¡Gracias por sumarte con buena onda!"
        )
        await asyncio.sleep(60)
        await msg.delete()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Mandá tu mensaje al admin o preguntá dudas. ¡Gracias!")

async def publicidad_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_link = f"tg://user?id={user.id}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📨 Responder", callback_data=f"responder_{user.id}")]])
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📢 Nuevo mensaje de @{user.username or user.first_name}:\n{update.message.text}\nContacto: {user_link}",
        reply_markup=keyboard
    )
    await update.message.reply_text("✅ Mensaje enviado al admin.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[1])
    reply_context[query.from_user.id] = user_id
    await query.message.reply_text("✍️ Escribí tu respuesta:")

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    target_id = reply_context.get(admin_id)

    if not target_id:
        await update.message.reply_text("❌ No hay contexto activo.")
        return

    await context.bot.send_message(chat_id=target_id, text=update.message.text)
    await update.message.reply_text("✅ Respuesta enviada.")
    del reply_context[admin_id]

async def reglas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📜 <b>Reglas:</b> No spam, No porno, No drogas, Respeto siempre.")

def main():
    app = Application.builder().token(TOKEN).defaults(Defaults(parse_mode="HTML")).rate_limiter(AIORateLimiter()).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglas", reglas))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, publicidad_chat))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, handle_messages))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, admin_reply))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
