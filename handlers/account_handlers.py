from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import login_account, get_client_for_account, safe_disconnect
import re

# Conversation states
(SINGLE_ADD, BULK_ADD_COUNT, BULK_ADD_SESSION) = range(3)

async def account_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle account button click"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Single Add", callback_data="single_add")],
        [InlineKeyboardButton("Bulk Add", callback_data="bulk_add")],
        [InlineKeyboardButton("Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📱 **Account Management**\n\nChoose an option:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def single_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start single account addition"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Please send your Telegram **session string**.\n\n"
        "You can get this from:\n"
        "1. Telethon StringSession\n"
        "2. Pyrogram StringSession\n\n"
        "Format: `session_string`",
        parse_mode="Markdown"
    )
    return SINGLE_ADD

async def single_add_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process single account session string"""
    session_string = update.message.text.strip()
    
    # Validate session string format (basic check)
    if len(session_string) < 10:
        await update.message.reply_text(
            "❌ Invalid session string format. Please try again."
        )
        return SINGLE_ADD
    
    # Try to login with the session
    progress_msg = await update.message.reply_text(
        "🔄 Logging in to account..."
    )
    
    success, me = await login_account(session_string)
    
    if success and me:
        # Check if account already exists
        existing = await db.get_account({"session_string": session_string})
        if existing:
            await progress_msg.edit_text(
                "⚠️ This account is already added to the bot."
            )
            return ConversationHandler.END
        
        # Save account to database
        account_data = {
            "session_string": session_string,
            "username": me.username or f"user_{me.id}",
            "id": me.id,
            "phone": me.phone,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "status": "active",
            "mode": "normal",
            "privacy": "normal",
            "is_hidden": False,
            "last_seen": None,
            "joined_at": me.date.isoformat() if hasattr(me, 'date') else None,
            "added_at": str(update.message.date)
        }
        
        await db.add_account(account_data)
        
        await progress_msg.edit_text(
            f"✅ **Account Added Successfully!**\n\n"
            f"👤 Username: @{me.username or 'Not set'}\n"
            f"🆔 ID: {me.id}\n"
            f"📱 Phone: {me.phone or 'Hidden'}\n"
            f"📝 Status: Active",
            parse_mode="Markdown"
        )
    else:
        await progress_msg.edit_text(
            "❌ Failed to login with the provided session string.\n\n"
            "Please make sure:\n"
            "• The session string is valid\n"
            "• You have a stable internet connection\n"
            "• Try regenerating the session string"
        )
    
    return ConversationHandler.END

async def bulk_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start bulk account addition"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📊 **Bulk Add Accounts**\n\n"
        "How many accounts do you want to add?\n"
        "Please send a number (1-100):",
        parse_mode="Markdown"
    )
    return BULK_ADD_COUNT

async def bulk_add_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process bulk add count"""
    try:
        count = int(update.message.text.strip())
        if count < 1 or count > 100:
            raise ValueError("Count must be between 1 and 100")
        
        context.user_data['bulk_count'] = count
        context.user_data['bulk_accounts'] = []
        context.user_data['bulk_current'] = 0
        
        await update.message.reply_text(
            f"📥 **Adding {count} accounts**\n\n"
            f"Please send session string for account #{1}\n"
            f"(`{count} sessions remaining`)",
            parse_mode="Markdown"
        )
        return BULK_ADD_SESSION
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number between 1 and 100."
        )
        return BULK_ADD_COUNT

async def bulk_add_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process bulk add session strings"""
    session_string = update.message.text.strip()
    current = context.user_data.get('bulk_current', 0)
    total = context.user_data.get('bulk_count', 0)
    
    if len(session_string) < 10:
        await update.message.reply_text(
            "❌ Invalid session string format. Please try again."
        )
        return BULK_ADD_SESSION
    
    # Try to login with the session
    progress_msg = await update.message.reply_text(
        f"🔄 Logging in to account #{current + 1}..."
    )
    
    success, me = await login_account(session_string)
    
    if success and me:
        # Check if account already exists
        existing = await db.get_account({"session_string": session_string})
        if existing:
            await progress_msg.edit_text(
                f"⚠️ Account #{current + 1} already exists in the bot.\n"
                f"Skipping..."
            )
        else:
            # Save account to database
            account_data = {
                "session_string": session_string,
                "username": me.username or f"user_{me.id}",
                "id": me.id,
                "phone": me.phone,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "status": "active",
                "mode": "normal",
                "privacy": "normal",
                "is_hidden": False,
                "last_seen": None,
                "joined_at": me.date.isoformat() if hasattr(me, 'date') else None,
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
                f"(`{total - current} sessions remaining`)",
                parse_mode="Markdown"
            )
            return BULK_ADD_SESSION
        else:
            # All accounts added
            await update.message.reply_text(
                f"✅ **Bulk Add Complete!**\n\n"
                f"📊 Successfully added: {len(context.user_data['bulk_accounts'])}/{total} accounts",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
    else:
        await progress_msg.edit_text(
            f"❌ Failed to add account #{current + 1}.\n"
            f"Please check the session string and try again."
        )
        return BULK_ADD_SESSION

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text(
        "❌ Operation cancelled."
    )
    return ConversationHandler.END
