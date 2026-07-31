from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import login_account
import re

# Conversation states
(SINGLE_ADD, BULK_ADD_COUNT, BULK_ADD_SESSION) = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text(
        "❌ Operation cancelled."
    )
    return ConversationHandler.END

async def account_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle account button click"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Single Add", callback_data="single_add")],
        [InlineKeyboardButton("📊 Bulk Add", callback_data="bulk_add")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📱 **Account Management**\n\n"
        "Choose an option:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def single_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start single account addition"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📝 **Single Account Addition**\n\n"
        "Please send your Telegram **session string**.\n\n"
        "How to get session string:\n"
        "1. Use Telethon: `StringSession()`\n"
        "2. Use Pyrogram: `StringSession()`\n\n"
        "Format: `1BQAN...` (long string)\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return SINGLE_ADD

async def single_add_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process single account session string"""
    session_string = update.message.text.strip()
    
    # Check for cancel
    if session_string.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    # Validate session string format (basic check)
    if len(session_string) < 10:
        await update.message.reply_text(
            "❌ Invalid session string format. Please send a valid session string.\n"
            "Send /cancel to cancel."
        )
        return SINGLE_ADD
    
    # Try to login with the session
    progress_msg = await update.message.reply_text(
        "🔄 Logging in to account... Please wait."
    )
    
    try:
        success, me = await login_account(session_string)
        
        if success and me:
            # Check if account already exists
            existing = await db.get_account({"session_string": session_string})
            if existing:
                await progress_msg.edit_text(
                    "⚠️ This account is already added to the bot.\n\n"
                    f"👤 Username: @{me.username or 'Not set'}\n"
                    f"🆔 ID: {me.id}"
                )
                return ConversationHandler.END
            
            # Save account to database
            account_data = {
                "session_string": session_string,
                "username": me.username or f"user_{me.id}",
                "id": me.id,
                "phone": me.phone or "Hidden",
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "status": "active",
                "mode": "normal",
                "privacy": "normal",
                "is_hidden": False,
                "last_seen": None,
                "added_at": str(update.message.date)
            }
            
            await db.add_account(account_data)
            
            await progress_msg.edit_text(
                f"✅ **Account Added Successfully!**\n\n"
                f"👤 Username: @{me.username or 'Not set'}\n"
                f"🆔 ID: {me.id}\n"
                f"📱 Phone: {me.phone or 'Hidden'}\n"
                f"📝 Status: Active\n"
                f"🎯 Mode: Normal",
                parse_mode="Markdown"
            )
        else:
            await progress_msg.edit_text(
                "❌ **Failed to login with the provided session string.**\n\n"
                "Please make sure:\n"
                "• The session string is valid and not expired\n"
                "• You have a stable internet connection\n"
                "• The account is not banned or limited\n\n"
                "Try regenerating the session string.\n"
                "Send /cancel to cancel."
            )
    except Exception as e:
        await progress_msg.edit_text(
            f"❌ Error: {str(e)[:100]}\n\n"
            "Please check the session string and try again.\n"
            "Send /cancel to cancel."
        )
        return SINGLE_ADD
    
    return ConversationHandler.END

async def bulk_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start bulk account addition"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📊 **Bulk Account Addition**\n\n"
        "How many accounts do you want to add?\n"
        "Please send a number (1-50):\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return BULK_ADD_COUNT

async def bulk_add_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process bulk add count"""
    text = update.message.text.strip()
    
    # Check for cancel
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    try:
        count = int(text)
        if count < 1 or count > 50:
            await update.message.reply_text(
                "❌ Please send a number between 1 and 50.\n"
                "Send /cancel to cancel."
            )
            return BULK_ADD_COUNT
        
        context.user_data['bulk_count'] = count
        context.user_data['bulk_accounts'] = []
        context.user_data['bulk_current'] = 0
        context.user_data['bulk_failed'] = []
        
        await update.message.reply_text(
            f"📥 **Adding {count} accounts**\n\n"
            f"Please send session string for account #{1}\n"
            f"({count} sessions remaining)\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return BULK_ADD_SESSION
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number.\n"
            "Send /cancel to cancel."
        )
        return BULK_ADD_COUNT

async def bulk_add_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process bulk add session strings"""
    session_string = update.message.text.strip()
    current = context.user_data.get('bulk_current', 0)
    total = context.user_data.get('bulk_count', 0)
    
    # Check for cancel
    if session_string.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    if len(session_string) < 10:
        await update.message.reply_text(
            f"❌ Invalid session string format for account #{current + 1}.\n"
            f"Please send a valid session string.\n"
            f"Send /cancel to cancel."
        )
        return BULK_ADD_SESSION
    
    # Try to login with the session
    progress_msg = await update.message.reply_text(
        f"🔄 Logging in to account #{current + 1}..."
    )
    
    try:
        success, me = await login_account(session_string)
        
        if success and me:
            # Check if account already exists
            existing = await db.get_account({"session_string": session_string})
            if existing:
                await progress_msg.edit_text(
                    f"⚠️ Account #{current + 1} already exists.\n"
                    f"👤 @{me.username or 'Not set'}\n"
                    f"Skipping..."
                )
            else:
                # Save account to database
                account_data = {
                    "session_string": session_string,
                    "username": me.username or f"user_{me.id}",
                    "id": me.id,
                    "phone": me.phone or "Hidden",
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "status": "active",
                    "mode": "normal",
                    "privacy": "normal",
                    "is_hidden": False,
                    "last_seen": None,
                    "added_at": str(update.message.date)
                }
                
                await db.add_account(account_data)
                context.user_data['bulk_accounts'].append(account_data)
                
                await progress_msg.edit_text(
                    f"✅ Account #{current + 1} added successfully!\n"
                    f"👤 @{me.username or 'Not set'}"
                )
            
            current += 1
            context.user_data['bulk_current'] = current
            
            if current < total:
                await update.message.reply_text(
                    f"📥 Send session for account #{current + 1}\n"
                    f"({total - current} sessions remaining)\n\n"
                    f"Send /cancel to cancel."
                )
                return BULK_ADD_SESSION
            else:
                # All accounts added
                success_count = len(context.user_data['bulk_accounts'])
                await update.message.reply_text(
                    f"✅ **Bulk Add Complete!**\n\n"
                    f"📊 Successfully added: {success_count}/{total} accounts\n"
                    f"❌ Failed: {total - success_count}\n\n"
                    f"Added accounts will be active and ready to use.",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        else:
            await progress_msg.edit_text(
                f"❌ Failed to add account #{current + 1}.\n"
                f"Please check the session string.\n\n"
                f"Send session for account #{current + 1} again\n"
                f"or send /cancel to stop."
            )
            return BULK_ADD_SESSION
    except Exception as e:
        await progress_msg.edit_text(
            f"❌ Error: {str(e)[:100]}\n\n"
            f"Please try again for account #{current + 1}.\n"
            f"Send /cancel to cancel."
        )
        return BULK_ADD_SESSION
