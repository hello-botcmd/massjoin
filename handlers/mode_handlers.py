import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import (
    get_client_for_account, safe_disconnect, update_status, set_privacy,
    stop_account_mode, apply_mode_to_account, get_stop_event, clear_stop_event
)
from telethon import types
import random

logger = logging.getLogger(__name__)

# Conversation states
WAIT_MODE_COUNTS = 0

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def mode_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mode button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎭 Send counts as: `mode1, mode2, mode3`\n"
        "Example: `5,3,2`\n\n"
        "*Mode 1* — Always online\n"
        "*Mode 2* — Online 2 min, then offline\n"
        "*Mode 3* — Hidden last seen\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return WAIT_MODE_COUNTS

async def mode_counts_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mode counts input"""
    uid = update.effective_user.id
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    # Parse counts
    try:
        parts = text.replace(' ', '').split(',')
        if len(parts) != 3:
            raise ValueError
        c1, c2, c3 = map(int, parts)
        if c1 < 0 or c2 < 0 or c3 < 0:
            raise ValueError
    except:
        await update.message.reply_text(
            "❌ Invalid. Use e.g.: `5,3,2`\n\n"
            "Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return WAIT_MODE_COUNTS
    
    total = c1 + c2 + c3
    accounts = await db.get_active_accounts()
    
    if len(accounts) < total:
        await update.message.reply_text(
            f"❌ Need {total} active accounts, but only {len(accounts)} available.",
        )
        return ConversationHandler.END
    
    # Stop any previous mode tasks for these accounts first
    for acc in accounts:
        await stop_account_mode(acc)
    
    # Distribute accounts randomly
    random.shuffle(accounts)
    mode_counts = [(1, c1), (2, c2), (3, c3)]
    assignments = []
    idx = 0
    for mode, count in mode_counts:
        for _ in range(count):
            assignments.append((accounts[idx], mode))
            idx += 1
    
    status_msg = await update.message.reply_text(f"⏳ Applying modes to {total} accounts...")
    
    results = []
    for acc, mode in assignments:
        msg = await apply_mode_to_account(acc, mode)
        results.append(msg)
        await asyncio.sleep(0.3)
    
    detail = "\n".join(results)
    if len(detail) > 3000:
        detail = detail[:3000] + "\n..."
    
    await status_msg.edit_text(
        f"🎭 *Mode Distribution Complete*\n\n"
        f"Mode 1 (always online): `{c1}`\n"
        f"Mode 2 (2 min online): `{c2}`\n"
        f"Mode 3 (hidden): `{c3}`\n\n"
        f"```\n{detail}\n```",
        parse_mode="Markdown"
    )
    return ConversationHandler.END
