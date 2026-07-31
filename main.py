import logging
import warnings
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from telegram.warnings import PTBUserWarning
from config import BOT_TOKEN, ALLOWED_USERS
from database import db
from handlers import (
    account_handlers, join_handlers, mode_handlers,
    reset_handlers, total_handlers, reaction_handlers,
    views_handlers, online_handlers, utils
)
import asyncio
from telethon import functions

warnings.filterwarnings("ignore", category=PTBUserWarning)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Add Account", callback_data="add_account"),
         InlineKeyboardButton("🔗 Join", callback_data="join")],
        [InlineKeyboardButton("🎯 Mode", callback_data="mode"),
         InlineKeyboardButton("🔄 Reset Profile", callback_data="reset")],
        [InlineKeyboardButton("📊 Total Accounts", callback_data="total"),
         InlineKeyboardButton("🎭 Reactions", callback_data="reaction")],
        [InlineKeyboardButton("👁️ Views", callback_data="views"),
         InlineKeyboardButton("🟢 All Online", callback_data="online")]
    ]
    await update.message.reply_text(
        "🤖 **Telegram Bot**\n\nWelcome! Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "main_menu":
        await start(update, context)
        return
    # Direct handlers for non-conversation buttons
    if data == "add_account":
        await account_handlers.account_button(update, context)
    elif data == "total":
        await total_handlers.total_button(update, context)
    elif data == "online":
        await online_handlers.online_button(update, context)
    elif data == "reset":
        await reset_handlers.reset_button(update, context)
    # Others (join, mode, reaction, views) are handled by conversation handlers

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force stop all ongoing operations for the user."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    # Set stop event for this user
    utils.set_stop_event(user_id)
    # Clear any user data
    context.user_data.clear()
    await update.message.reply_text(
        "🛑 **All processes stopped!**\n\n"
        "Ongoing operations have been cancelled.\n"
        "Use /start to return to menu.",
        parse_mode="Markdown"
    )

async def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ An error occurred. Try again.")
    except:
        pass

async def post_startup():
    await db.initialize()
    logger.info("Database initialized")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(post_startup())

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("cancel", account_handlers.cancel_conversation))

    # Account conversation
    app.add_handler(account_handlers.get_add_account_handler())

    # Join conversation
    join_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(join_handlers.join_entry, pattern="^join$")],
        states={
            join_handlers.WAIT_JOIN_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, join_handlers.join_link_handle)
            ],
            join_handlers.WAIT_JOIN_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, join_handlers.join_count_handle)
            ],
            join_handlers.WAIT_JOIN_TIMING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, join_handlers.join_timing_handle)
            ],
        },
        fallbacks=[CommandHandler("cancel", join_handlers.cancel_conversation)],
        name="join_conversation"
    )
    app.add_handler(join_conv)

    # Mode conversation
    mode_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(mode_handlers.mode_button, pattern="^mode$")],
        states={
            mode_handlers.WAIT_MODE_COUNTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mode_handlers.mode_counts_handle)
            ],
        },
        fallbacks=[CommandHandler("cancel", mode_handlers.cancel_conversation)],
        name="mode_conversation"
    )
    app.add_handler(mode_conv)

    # Reaction conversation (placeholder, you can implement similarly)
    reaction_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reaction_handlers.reaction_button, pattern="^reaction$")],
        states={
            reaction_handlers.REACTION_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reaction_handlers.reaction_link)
            ],
            reaction_handlers.REACTION_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reaction_handlers.reaction_count)
            ],
            reaction_handlers.REACTION_TYPES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reaction_handlers.reaction_types)
            ],
        },
        fallbacks=[CommandHandler("cancel", reaction_handlers.cancel_conversation)],
        name="reaction_conversation"
    )
    app.add_handler(reaction_conv)

    # Views conversation
    views_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(views_handlers.views_button, pattern="^views$")],
        states={
            views_handlers.VIEWS_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, views_handlers.views_link)
            ],
            views_handlers.VIEWS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, views_handlers.views_count)
            ],
        },
        fallbacks=[CommandHandler("cancel", views_handlers.cancel_conversation)],
        name="views_conversation"
    )
    app.add_handler(views_conv)

    # Menu callback handler for non-conversation callbacks
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^(main_menu|add_account|total|online|reset)$"))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Bot started...")
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
