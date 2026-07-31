import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from client_manager import client_manager

logger = logging.getLogger(__name__)

# Conversation states
SINGLE_SESSION, BULK_COUNT, BULK_SESSION = range(10, 13)
PHONE_NUMBER, OTP_CODE, TWO_FA = range(13, 16)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation."""
    phone = context.user_data.get("login_phone")
    if phone:
        await client_manager.cancel_pending_login(phone)
    await update.message.reply_text("❌ Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def account_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle account button click."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📱 Single Add", callback_data="add_single")],
        [InlineKeyboardButton("📋 Bulk Add", callback_data="add_bulk")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📥 **Add Account**\n\nChoose how you want to add accounts:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def add_single_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start single account addition."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔑 Session String", callback_data="add_session_string")],
        [InlineKeyboardButton("📱 Phone Login", callback_data="add_phone_login")],
        [InlineKeyboardButton("🔙 Back", callback_data="add_account")],
    ]
    
    await query.edit_message_text(
        "📱 **Single Add**\n\nChoose how to add the account:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SINGLE_SESSION

async def add_via_session_string(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start session string flow."""
    query = update.callback_query
    await query.answer()
    context.user_data["add_method"] = "session"
    
    await query.edit_message_text(
        "🔑 **Session String Method**\n\n"
        "Please send the Telethon session string.\n\n"
        "💡 How to get session string:\n"
        "1. Use Telethon: `StringSession()`\n"
        "2. Use Pyrogram: `StringSession()`\n\n"
        "Format: `1BQAN...` (long string)\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return SINGLE_SESSION

async def add_via_phone_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start phone login flow."""
    query = update.callback_query
    await query.answer()
    context.user_data["add_method"] = "phone"
    
    await query.edit_message_text(
        "📱 **Phone Login**\n\n"
        "Send the phone number in international format.\n"
        "Example: `+1234567890`\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return PHONE_NUMBER

async def handle_single_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle session string input."""
    method = context.user_data.get("add_method", "session")
    
    if method == "session":
        return await handle_session_string(update, context)
    else:
        await update.message.reply_text("❌ Something went wrong. Use /cancel and try again.")
        return ConversationHandler.END

async def handle_session_string(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validate and add account via session string."""
    session_string = update.message.text.strip()
    
    # Check for cancel
    if session_string.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ Validating session...")
    
    success, phone, error = await client_manager.validate_session(session_string)
    
    if not success:
        await status_msg.edit_text(
            f"❌ **Invalid Session**\n\nError: {error}\n\n"
            f"Please try again or send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return SINGLE_SESSION
    
    # Check if account exists
    existing = await db.get_account(phone)
    if existing:
        await status_msg.edit_text(
            f"⚠️ Account {phone} already exists in the database.\n\n"
            f"Send another session or /cancel to cancel.",
            parse_mode="Markdown"
        )
        return SINGLE_SESSION
    
    # Add account
    added = await db.add_account(phone, session_string)
    if added:
        await status_msg.edit_text(
            f"✅ **Account Added Successfully!**\n\n"
            f"📱 Phone: `{phone}`\n\n"
            f"Use /start to go back to main menu.",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(
            f"❌ Failed to add account. Please try again.",
            parse_mode="Markdown"
        )
        return SINGLE_SESSION
    
    return ConversationHandler.END

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input for login."""
    phone = update.message.text.strip()
    
    # Check for cancel
    if phone.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ Sending OTP code...")
    
    try:
        client, code_hash = await client_manager.start_phone_login(phone)
        context.user_data["login_phone"] = phone
        await status_msg.edit_text(
            f"✅ OTP sent to `{phone}`\n\n"
            f"📱 Check your **Telegram app** (the code arrives in Telegram, not SMS)\n\n"
            f"Please send the OTP code you received.\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return OTP_CODE
    except ValueError as e:
        await status_msg.edit_text(
            f"❌ {str(e)}\n\n"
            f"Try a different phone or use session string instead.\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        await client_manager.cancel_pending_login(phone)
        return PHONE_NUMBER
    except Exception as e:
        error_text = str(e)[:250]
        await status_msg.edit_text(
            f"❌ Failed to send OTP.\n"
            f"Error: `{error_text}`\n\n"
            f"Possible causes:\n"
            f"• Check API_ID and API_HASH in config.py\n"
            f"• Phone number format should be +1234567890\n"
            f"• The phone might not have a Telegram account\n\n"
            f"Try again or send /cancel to cancel.",
            parse_mode="Markdown"
        )
        await client_manager.cancel_pending_login(phone)
        return PHONE_NUMBER

async def handle_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle OTP code input."""
    code = update.message.text.strip()
    phone = context.user_data.get("login_phone")
    
    if not phone:
        await update.message.reply_text("❌ Login session expired. Please start over.\n\nSend /cancel to cancel.")
        return ConversationHandler.END
    
    # Check for cancel
    if code.lower() == '/cancel':
        await client_manager.cancel_pending_login(phone)
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ Verifying OTP...")
    
    success, result, error = await client_manager.submit_otp(phone, code)
    
    if success:
        # result is the session_string
        added = await db.add_account(phone, result)
        if added:
            await status_msg.edit_text(
                f"✅ **Account Added Successfully!**\n\n"
                f"📱 Phone: `{phone}`\n\n"
                f"Use /start for main menu.",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(
                f"⚠️ Account {phone} already existed, but login successful.\n\n"
                f"Use /start for main menu.",
                parse_mode="Markdown"
            )
        context.user_data.clear()
        return ConversationHandler.END
    elif error == "2FA_REQUIRED":
        context.user_data["login_awaiting_2fa"] = True
        await status_msg.edit_text(
            f"🔐 **Two-Factor Authentication Required**\n\n"
            f"Account `{phone}` has 2FA enabled.\n"
            f"Please send your 2FA password.\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return TWO_FA
    else:
        await status_msg.edit_text(
            f"❌ Invalid OTP: {error}\n\n"
            f"Please try again or send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return OTP_CODE

async def handle_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 2FA password input."""
    password = update.message.text.strip()
    phone = context.user_data.get("login_phone")
    
    if not phone:
        await update.message.reply_text("❌ Login session expired. Start over.\n\nSend /cancel.")
        return ConversationHandler.END
    
    # Check for cancel
    if password.lower() == '/cancel':
        await client_manager.cancel_pending_login(phone)
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ Verifying 2FA password...")
    
    success, session_string, error = await client_manager.submit_2fa(phone, password)
    
    if success:
        added = await db.add_account(phone, session_string)
        if added:
            await status_msg.edit_text(
                f"✅ **Account Added Successfully!**\n\n"
                f"📱 Phone: `{phone}`\n\n"
                f"Use /start for main menu.",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(
                f"⚠️ Account {phone} already existed, but login successful.\n\n"
                f"Use /start for main menu.",
                parse_mode="Markdown"
            )
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await status_msg.edit_text(
            f"❌ Invalid 2FA password: {error}\n\n"
            f"Please try again or send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return TWO_FA

async def add_bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start bulk addition."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📋 **Bulk Add**\n\n"
        "How many accounts do you want to add?\n"
        "Please send a number (1-50):\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return BULK_COUNT

async def handle_bulk_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk count input."""
    text = update.message.text.strip()
    
    # Check for cancel
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text(
            "❌ Please send a valid number greater than 0.\n\n"
            "Send /cancel to cancel."
        )
        return BULK_COUNT
    
    total = int(text)
    if total > 50:
        await update.message.reply_text(
            "❌ Maximum 50 accounts allowed per bulk operation.\n\n"
            "Please send a number between 1-50.\n"
            "Send /cancel to cancel."
        )
        return BULK_COUNT
    
    context.user_data["bulk_total"] = total
    context.user_data["bulk_index"] = 0
    context.user_data["bulk_list"] = []
    context.user_data["bulk_failed"] = []
    
    await update.message.reply_text(
        f"📋 **Bulk Add** — {total} accounts\n\n"
        f"Send session string **1/{total}**:\n\n"
        f"Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return BULK_SESSION

async def handle_bulk_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk session input."""
    session_string = update.message.text.strip()
    index = context.user_data.get("bulk_index", 0) + 1
    total = context.user_data.get("bulk_total", 0)
    
    # Check for cancel
    if session_string.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text(f"⏳ Validating session {index}/{total}...")
    
    success, phone, error = await client_manager.validate_session(session_string)
    
    if not success:
        await status_msg.edit_text(
            f"❌ **Invalid Session** ({index}/{total})\n"
            f"Error: {error}\n\n"
            f"Please send a valid session string or /cancel to cancel.",
            parse_mode="Markdown"
        )
        return BULK_SESSION
    
    # Check if account exists
    existing = await db.get_account(phone)
    if existing:
        await status_msg.edit_text(
            f"⚠️ Account {phone} already exists. Skipping.\n\n"
            f"Send session **{index}/{total}** (this one was skipped):",
            parse_mode="Markdown"
        )
        context.user_data["bulk_index"] = index
        return BULK_SESSION
    
    # Add account
    added = await db.add_account(phone, session_string)
    if added:
        bulk_list = context.user_data.get("bulk_list", [])
        bulk_list.append(phone)
        context.user_data["bulk_list"] = bulk_list
        await status_msg.edit_text(f"✅ Account {phone} added! ({index}/{total})")
    else:
        await status_msg.edit_text(f"❌ Failed to add account {phone}. Skipping.")
    
    context.user_data["bulk_index"] = index
    
    if index >= total:
        all_phones = context.user_data.get("bulk_list", [])
        phone_list = "\n".join(f"• `{p}`" for p in all_phones) if all_phones else "No accounts added."
        await update.message.reply_text(
            f"🎉 **Bulk Add Complete!**\n\n"
            f"{len(all_phones)} accounts added successfully.\n\n"
            f"Added phones:\n{phone_list}\n\n"
            f"Use /start for main menu.",
            parse_mode="Markdown"
        )
        for key in ["bulk_total", "bulk_index", "bulk_list", "bulk_failed"]:
            context.user_data.pop(key, None)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            f"Send session string **{index + 1}/{total}**:\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return BULK_SESSION

def get_add_account_handler():
    """Return the ConversationHandler for adding accounts."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_single_start, pattern="^add_single$"),
            CallbackQueryHandler(add_bulk_start, pattern="^add_bulk$"),
        ],
        states={
            SINGLE_SESSION: [
                CallbackQueryHandler(add_via_session_string, pattern="^add_session_string$"),
                CallbackQueryHandler(add_via_phone_login, pattern="^add_phone_login$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_single_session),
            ],
            PHONE_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number),
            ],
            OTP_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_otp),
            ],
            TWO_FA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_2fa),
            ],
            BULK_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_count),
            ],
            BULK_SESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_session),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
        ],
        per_message=False
    )
