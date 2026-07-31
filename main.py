import logging
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
from config import BOT_TOKEN, ALLOWED_USERS, OWNER_ID
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

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global tasks
online_tasks = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    # Check if user is authorized
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text(
            "⛔ You are not authorized to use this bot."
        )
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
        "🤖 **Telegram Bot**\n\n"
        "Welcome! Choose an option below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
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
            "🤖 **Telegram Bot**\n\n"
            "Choose an option below:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Route to appropriate handler
    if data == "add_account":
        await account_handlers.account_button(update, context)
    elif data == "single_add":
        await account_handlers.single_add_start(update, context)
    elif data == "bulk_add":
        await account_handlers.bulk_add_start(update, context)
    elif data == "join":
        await join_handlers.join_button(update, context)
    elif data == "mode":
        await mode_handlers.mode_button(update, context)
    elif data == "reset":
        await reset_handlers.reset_button(update, context)
    elif data == "total":
        await total_handlers.total_button(update, context)
    elif data == "reaction":
        await reaction_handlers.reaction_button(update, context)
    elif data == "views":
        await views_handlers.views_button(update, context)
    elif data == "online":
        await online_handlers.online_button(update, context)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command - stop all ongoing processes"""
    user_id = update.effective_user.id
    
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    
    # Clear all user data
    context.user_data.clear()
    
    # Stop all running tasks
    for task_id, task in online_tasks.items():
        if not task.done():
            task.cancel()
    online_tasks.clear()
    
    await update.message.reply_text(
        "🛑 **All processes stopped!**\n\n"
        "All ongoing operations have been cancelled.",
        parse_mode="Markdown"
    )

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove command to remove accounts from chats"""
    user_id = update.effective_user.id
    
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Please provide a chat ID to remove accounts from.\n"
            "Usage: `/remove chat_id`",
            parse_mode="Markdown"
        )
        return
    
    try:
        chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid chat ID. Please provide a valid numeric ID."
        )
        return
    
    await update.message.reply_text(
        f"🔄 Removing accounts from chat {chat_id}..."
    )
    
    # Get all accounts
    accounts = await db.get_all_accounts()
    success_count = 0
    failed_count = 0
    
    for account in accounts:
        client = None
        try:
            client = await utils.get_client_for_account(account)
            if client:
                success, error = await utils.leave_channel(client, str(chat_id))
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                await utils.safe_disconnect(client)
        except Exception:
            failed_count += 1
            await utils.safe_disconnect(client)
    
    await update.message.reply_text(
        f"✅ **Removal Complete!**\n\n"
        f"📊 Total accounts: {len(accounts)}\n"
        f"✅ Removed: {success_count}\n"
        f"❌ Failed: {failed_count}"
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
    # Initialize database
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(post_startup())
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("remove", remove_command))
    
    # Add callback handler
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Account handlers - Use per_message=False to avoid warnings with mixed handlers
    account_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(account_handlers.single_add_start, pattern="^single_add$"),
            CallbackQueryHandler(account_handlers.bulk_add_start, pattern="^bulk_add$"),
        ],
        states={
            account_handlers.SINGLE_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.single_add_session)
            ],
            account_handlers.BULK_ADD_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.bulk_add_count)
            ],
            account_handlers.BULK_ADD_SESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.bulk_add_session)
            ],
        },
        fallbacks=[
            CommandHandler("stop", account_handlers.cancel_conversation),
            CommandHandler("cancel", account_handlers.cancel_conversation),
        ],
        per_message=False
    )
    application.add_handler(account_conv)
    
    # Join handlers
    join_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(join_handlers.join_button, pattern="^join$")],
        states={
            join_handlers.JOIN_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, join_handlers.join_link)
            ],
            join_handlers.JOIN_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, join_handlers.join_count)
            ],
            join_handlers.JOIN_TIMING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, join_handlers.join_timing)
            ],
        },
        fallbacks=[
            CommandHandler("stop", join_handlers.cancel_conversation),
            CommandHandler("cancel", join_handlers.cancel_conversation),
        ],
        per_message=False
    )
    application.add_handler(join_conv)
    
    # Mode handlers
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
        fallbacks=[
            CommandHandler("stop", mode_handlers.cancel_conversation),
            CommandHandler("cancel", mode_handlers.cancel_conversation),
        ],
        per_message=False
    )
    application.add_handler(mode_conv)
    
    # Reaction handlers
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
        fallbacks=[
            CommandHandler("stop", reaction_handlers.cancel_conversation),
            CommandHandler("cancel", reaction_handlers.cancel_conversation),
        ],
        per_message=False
    )
    application.add_handler(reaction_conv)
    
    # Views handlers
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
        fallbacks=[
            CommandHandler("stop", views_handlers.cancel_conversation),
            CommandHandler("cancel", views_handlers.cancel_conversation),
        ],
        per_message=False
    )
    application.add_handler(views_conv)
    
    # Add reset and total handlers
    application.add_handler(CallbackQueryHandler(reset_handlers.reset_button, pattern="^reset$"))
    application.add_handler(CallbackQueryHandler(total_handlers.total_button, pattern="^total$"))
    application.add_handler(CallbackQueryHandler(online_handlers.online_button, pattern="^online$"))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
