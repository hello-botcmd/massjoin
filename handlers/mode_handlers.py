from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_client_for_account, update_status, set_privacy, safe_disconnect
import asyncio
import random
from telethon import functions, types

# Conversation states
(MODE_COUNT1, MODE_COUNT2, MODE_COUNT3) = range(3)

async def mode_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mode button click"""
    query = update.callback_query
    await query.answer()
    
    total_accounts = await db.get_account_count({"status": "active"})
    
    if total_accounts == 0:
        await query.edit_message_text(
            "❌ No active accounts found. Please add accounts first."
        )
        return
    
    await query.edit_message_text(
        f"📊 **Mode Distribution**\n\n"
        f"👤 Total active accounts: {total_accounts}\n\n"
        f"Please specify how many accounts should go to **Mode 1**\n"
        f"(Accounts will remain online forever):",
        parse_mode="Markdown"
    )
    return MODE_COUNT1

async def mode_count1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process mode 1 count"""
    try:
        count1 = int(update.message.text.strip())
        total = await db.get_account_count({"status": "active"})
        
        if count1 < 0 or count1 > total:
            await update.message.reply_text(
                f"❌ Please send a number between 0 and {total}."
            )
            return MODE_COUNT1
        
        context.user_data['mode_count1'] = count1
        
        await update.message.reply_text(
            f"📊 **Mode Distribution**\n\n"
            f"Mode 1: {count1} accounts\n\n"
            f"Please specify how many accounts should go to **Mode 2**\n"
            f"(Accounts will be online for 2 minutes, then offline):",
            parse_mode="Markdown"
        )
        return MODE_COUNT2
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number."
        )
        return MODE_COUNT1

async def mode_count2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process mode 2 count"""
    try:
        count2 = int(update.message.text.strip())
        total = await db.get_account_count({"status": "active"})
        count1 = context.user_data.get('mode_count1', 0)
        
        if count2 < 0 or count1 + count2 > total:
            await update.message.reply_text(
                f"❌ Please send a number between 0 and {total - count1}."
            )
            return MODE_COUNT2
        
        context.user_data['mode_count2'] = count2
        
        await update.message.reply_text(
            f"📊 **Mode Distribution**\n\n"
            f"Mode 1: {count1}\n"
            f"Mode 2: {count2}\n\n"
            f"Please specify how many accounts should go to **Mode 3**\n"
            f"(Accounts will hide their last seen):",
            parse_mode="Markdown"
        )
        return MODE_COUNT3
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number."
        )
        return MODE_COUNT2

async def mode_count3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process mode 3 count and apply modes"""
    try:
        count3 = int(update.message.text.strip())
        total = await db.get_account_count({"status": "active"})
        count1 = context.user_data.get('mode_count1', 0)
        count2 = context.user_data.get('mode_count2', 0)
        
        if count3 < 0 or count1 + count2 + count3 > total:
            await update.message.reply_text(
                f"❌ Please send a number between 0 and {total - count1 - count2}."
            )
            return MODE_COUNT3
        
        # Get all active accounts
        accounts = await db.get_active_accounts()
        random.shuffle(accounts)
        
        mode1_accounts = accounts[:count1]
        mode2_accounts = accounts[count1:count1 + count2]
        mode3_accounts = accounts[count1 + count2:count1 + count2 + count3]
        
        # Apply modes
        await update.message.reply_text(
            f"🔄 Applying modes to {total} accounts...\n"
            f"Mode 1: {len(mode1_accounts)}\n"
            f"Mode 2: {len(mode2_accounts)}\n"
            f"Mode 3: {len(mode3_accounts)}"
        )
        
        # Apply mode 1 (always online)
        for account in mode1_accounts:
            await db.update_account(
                {"_id": account["_id"]},
                {"mode": "mode1", "privacy": "normal", "is_hidden": False}
            )
            # Start online monitor for this account
            asyncio.create_task(mode1_monitor(account))
        
        # Apply mode 2 (2 min online, then offline)
        for account in mode2_accounts:
            await db.update_account(
                {"_id": account["_id"]},
                {"mode": "mode2", "privacy": "normal", "is_hidden": False}
            )
            asyncio.create_task(mode2_monitor(account))
        
        # Apply mode 3 (hide last seen)
        for account in mode3_accounts:
            await db.update_account(
                {"_id": account["_id"]},
                {"mode": "mode3", "privacy": "hidden", "is_hidden": True}
            )
            # Hide last seen
            client = await get_client_for_account(account)
            if client:
                try:
                    await set_privacy(
                        client,
                        types.InputPrivacyKeyStatusTimestamp(),
                        types.InputPrivacyRuleAllowAll()
                    )
                    await update_status(client, offline=False)
                except Exception:
                    pass
                await safe_disconnect(client)
        
        await update.message.reply_text(
            f"✅ **Mode Distribution Complete!**\n\n"
            f"📊 Mode 1: {len(mode1_accounts)} accounts (Always Online)\n"
            f"📊 Mode 2: {len(mode2_accounts)} accounts (2 min Online)\n"
            f"📊 Mode 3: {len(mode3_accounts)} accounts (Hidden Last Seen)"
        )
        
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number."
        )
        return MODE_COUNT3

async def mode1_monitor(account):
    """Monitor mode 1 accounts - keep them online forever"""
    while True:
        try:
            client = await get_client_for_account(account)
            if client:
                await update_status(client, offline=False)
                await safe_disconnect(client)
            await asyncio.sleep(30)  # Check every 30 seconds
        except Exception:
            await asyncio.sleep(10)

async def mode2_monitor(account):
    """Monitor mode 2 accounts - online for 2 minutes, then offline"""
    client = None
    try:
        client = await get_client_for_account(account)
        if client:
            # Set online
            await update_status(client, offline=False)
            await asyncio.sleep(120)  # 2 minutes
            # Set offline
            await update_status(client, offline=True)
    except Exception:
        pass
    finally:
        await safe_disconnect(client)
