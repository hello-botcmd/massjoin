from telegram import Update
from telegram.ext import ContextTypes
from database import db

async def total_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle total accounts button click"""
    query = update.callback_query
    await query.answer()
    
    total = await db.get_account_count()
    active = await db.get_account_count({"status": "active"})
    inactive = await db.get_account_count({"status": "inactive"})
    mode1 = await db.get_account_count({"mode": "mode1"})
    mode2 = await db.get_account_count({"mode": "mode2"})
    mode3 = await db.get_account_count({"mode": "mode3"})
    
    # Get recent accounts
    recent_accounts = await db.get_all_accounts()
    recent_accounts = recent_accounts[-5:] if recent_accounts else []
    
    message = "📊 **Account Statistics**\n\n"
    message += f"📱 **Total Accounts:** {total}\n"
    message += f"✅ **Active:** {active}\n"
    message += f"❌ **Inactive:** {inactive}\n\n"
    
    message += f"🎯 **Mode Distribution:**\n"
    message += f"• Mode 1 (Always Online): {mode1}\n"
    message += f"• Mode 2 (2 min Online): {mode2}\n"
    message += f"• Mode 3 (Hidden): {mode3}\n\n"
    
    if recent_accounts:
        message += f"📋 **Recent Accounts:**\n"
        for acc in recent_accounts:
            username = acc.get('username', 'Unknown')
            mode = acc.get('mode', 'normal')
            status = acc.get('status', 'unknown')
            message += f"• @{username} ({mode}) - {status}\n"
    
    await query.edit_message_text(
        message,
        parse_mode="Markdown"
    )
