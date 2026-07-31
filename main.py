import logging
import warnings
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from telegram.warnings import PTBUserWarning
from config import BOT_TOKEN, ALLOWED_USERS
from database import db
from handlers import (
    account_handlers,
    join_handlers,
    mode_handlers,
    reset_handlers,
    total_handlers,
    reaction_handlers,
    views_handlers,
    online_handlers,
    utils
)
import asyncio

# Suppress PTB warnings
warnings.filterwarnings("ignore", category=PTBUserWarning)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Account", callback_data="add_account"),
            InlineKeyboardButton("🔗 Join", callback_data="join")
        ],
        [
            InlineKeyboardButton("🎯 Mode", callback_data="mode"),
            InlineKeyboardButton("🔄 Reset Profile", callback_data="reset")
        ],
        [
            InlineKeyboardButton("📊 Total Accounts", callback_data="total"),
            InlineKeyboardButton("🎭 Reactions", callback_data="reaction")
        ],
        [
            InlineKeyboardButton("👁️ Views", callback_data="views"),
            InlineKeyboardButton("🟢 All Online", callback_data="online")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 **Telegram Bot**\n\nWelcome! Choose an option below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu navigation callbacks"""
    query = update.callback_query
    data = query.data
    
    if data == "main_menu":
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Account", callback_data="add_account"),
                InlineKeyboardButton("🔗 Join", callback_data="join")
            ],
            [
                InlineKeyboardButton("🎯 Mode", callback_data="mode"),
                InlineKeyboardButton("🔄 Reset Profile", callback_data="reset")
            ],
            [
                InlineKeyboardButton("📊 Total Accounts", callback_data="total"),
                InlineKeyboardButton("🎭 Reactions", callback_data="reaction")
            ],
            [
                InlineKeyboardButton("👁️ Views", callback_data="views"),
                InlineKeyboardButton("🟢 All Online", callback_data="online")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 **Telegram Bot**\n\nChoose an option below:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Route to specific handlers
    if data == "add_account":
        await account_handlers.account_button(update, context)
    elif data == "total":
        await total_handlers.total_button(update, context)
    elif data == "online":
        await online_handlers.online_button(update, context)
    elif data == "reset":
        await reset_handlers.reset_button(update, context)
    # Let conversation handlers handle join, mode, reaction, views

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command"""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    
    context.user_data.clear()
    await update.message.reply_text(
        "🛑 **All processes stopped!**\n\nAll ongoing operations have been cancelled.",
        parse_mode="Markdown"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again later."
            )
    except:
        pass

async def post_startup():
    """Initialize database connection"""
    await db.initialize()
    logger.info("Database initialized")

def main():
    """Main function to start the bot"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(post_startup())
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop_command))
    
    # Add conversation handlers FIRST
    application.add_handler(account_handlers.get_add_account_handler())
    
    # Join conversation handler
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
    application.add_handler(join_conv)
    
    # Mode conversation handler
    mode_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(mode_handlers.mode_button, pattern="^mode$")],
        states={
            mode_handlers.MODE_COUNT1: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mode_handlers.mode_count1)
            ],
            mode_handlers.MODE_COUNT2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mode_handlers.mode_count2)
            ],
            mode_handlers.MODE_COUNT3: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mode_handlers.mode_count3)
            ],
        },
        fallbacks=[CommandHandler("cancel", mode_handlers.cancel_conversation)],
        name="mode_conversation"
    )
    application.add_handler(mode_conv)
    
    # Reaction conversation handler
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
    application.add_handler(reaction_conv)
    
    # Views conversation handler
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
    application.add_handler(views_conv)
    
    # Add menu callback handler - only for specific patterns
    application.add_handler(
        CallbackQueryHandler(
            main_menu_callback,
            pattern="^(main_menu|add_account|total|online|reset)$"
        )
    )
    
    application.add_error_handler(error_handler)
    
    logger.info("Bot started...")
    application.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
