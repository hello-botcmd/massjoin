from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_client_for_account, update_status, set_privacy, safe_disconnect
from telethon import functions, types
import asyncio
import random

# Conversation states
(MODE_COUNT1, MODE_COUNT2, MODE_COUNT3) = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

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
        f"(Accounts will remain online forever):\n\n"
        f"Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return MODE_COUNT1

async def mode_count1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process mode 1 count"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    try:
        count1 = int(text)
        total = await db.get_account_count({"status": "active"})
        
        if count1 < 0 or count1 > total:
            await update.message.reply_text(
                f"❌ Please send a number between 0 and {total}.\n\n"
                f"Send /cancel to cancel."
            )
            return MODE_COUNT1
        
        context.user_data['mode_count1'] = count1
        
        await update.message.reply_text(
            f"📊 **Mode Distribution**\n\n"
            f"Mode 1: {count1} accounts\n\n"
            f"Please specify how many accounts should go to **Mode 2**\n"
            f"(Accounts will be online for 2 minutes, then offline):\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return MODE_COUNT2
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number.\n\n"
            f"Send /cancel to cancel."
        )
        return MODE_COUNT1

async def mode_count2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process mode 2 count"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    try:
        count2 = int(text)
        total = await db.get_account_count({"status": "active"})
        count1 = context.user_data.get('mode_count1', 0)
        
        if count2 < 0 or count1 + count2 > total:
            await update.message.reply_text(
                f"❌ Please send a number between 0 and {total - count1}.\n\n"
                f"Send /cancel to cancel."
            )
            return MODE_COUNT2
        
        context.user_data['mode_count2'] = count2
        
        await update.message.reply_text(
            f"📊 **Mode Distribution**\n\n"
            f"Mode 1: {count1}\n"
            f"Mode 2: {count2}\n\n"
            f"Please specify how many accounts should go to **Mode 3**\n"
            f"(Accounts will hide their last seen):\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return MODE_COUNT3
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number.\n\n"
            f"Send /cancel to cancel."
        )
        return MODE_COUNT2

async def mode_count3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process mode 3 count and apply modes"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    try:
        count3 = int(text)
        total = await db.get_account_count({"status": "active"})
        count1 = context.user_data.get('mode_count1', 0)
        count2 = context.user_data.get('mode_count2', 0)
        
        if count3 < 0 or count1 + count2 + count3 > total:
            await update.message.reply_text(
                f"❌ Please send a number between 0 and {total - count1 - count2}.\n\n"
                f"Send /cancel to cancel."
            )
            return MODE_COUNT3
        
        # Get all active accounts
        accounts = await db.get_active_accounts()
        random.shuffle(accounts)
        
        mode1_accounts = accounts[:count1]
        mode2_accounts = accounts[count1:count1 + count2]
        mode3_accounts = accounts[count1 + count2:count1 + count2 + count3]
        
        # Apply modes
        status_msg = await update.message.reply_text(
            f"🔄 Applying modes to {total} accounts...\n"
            f"Mode 1: {len(mode1_accounts)}\n"
            f"Mode 2: {len(mode2_accounts)}\n"
            f"Mode 3: {len(mode3_accounts)}\n\n"
            f"Starting..."
        )
        
        # Apply mode 1 (always online)
        for idx, account in enumerate(mode1_accounts):
            phone = account.get("_id", "unknown")
            await db.update_account(
                phone,
                {"mode": "mode1", "privacy": "normal", "is_hidden": False}
            )
            # Start online monitor for this account
            asyncio.create_task(mode1_monitor(account))
            if (idx + 1) % 10 == 0:
                await status_msg.edit_text(
                    f"🔄 Applying Mode 1... {idx + 1}/{len(mode1_accounts)}"
                )
        
        # Apply mode 2 (2 min online, then offline)
        for idx, account in enumerate(mode2_accounts):
            phone = account.get("_id", "unknown")
            await db.update_account(
                phone,
                {"mode": "mode2", "privacy": "normal", "is_hidden": False}
            )
            asyncio.create_task(mode2_monitor(account))
            if (idx + 1) % 10 == 0:
                await status_msg.edit_text(
                    f"🔄 Applying Mode 2... {idx + 1}/{len(mode2_accounts)}"
                )
        
        # Apply mode 3 (hide last seen)
        for idx, account in enumerate(mode3_accounts):
            phone = account.get("_id", "unknown")
            await db.update_account(
                phone,
                {"mode": "mode3", "privacy": "hidden", "is_hidden": True}
            )
            # Hide last seen
            client = await get_client_for_account(account)
            if client:
                try:
                    await set_privacy(
                        client,
                        types.InputPrivacyKeyStatusTimestamp(),
                        types.InputPrivacyRuleDisallowAll()
                    )
                    await update_status(client, offline=False)
                except Exception as e:
                    print(f"Error hiding last seen: {e}")
                await safe_disconnect(client)
            if (idx + 1) % 10 == 0:
                await status_msg.edit_text(
                    f"🔄 Applying Mode 3... {idx + 1}/{len(mode3_accounts)}"
                )
        
        await status_msg.edit_text(
            f"✅ **Mode Distribution Complete!**\n\n"
            f"📊 Mode 1: {len(mode1_accounts)} accounts (Always Online)\n"
            f"📊 Mode 2: {len(mode2_accounts)} accounts (2 min Online)\n"
            f"📊 Mode 3: {len(mode3_accounts)} accounts (Hidden Last Seen)"
        )
        
        # Clean up
        for key in ['mode_count1', 'mode_count2', 'mode_count3']:
            context.user_data.pop(key, None)
        
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number.\n\n"
            f"Send /cancel to cancel."
        )
        return MODE_COUNT3

async def mode1_monitor(account):
    """Monitor mode 1 accounts - keep them online forever"""
    phone = account.get("_id", "unknown")
    while True:
        try:
            client = await get_client_for_account(account)
            if client:
                await update_status(client, offline=False)
                await safe_disconnect(client)
            await asyncio.sleep(30)  # Check every 30 seconds
        except Exception as e:
            print(f"Mode 1 monitor error for {phone}: {e}")
            await asyncio.sleep(10)

async def mode2_monitor(account):
    """Monitor mode 2 accounts - online for 2 minutes, then offline"""
    phone = account.get("_id", "unknown")
    client = None
    try:
        client = await get_client_for_account(account)
        if client:
            # Set online
            await update_status(client, offline=False)
            await asyncio.sleep(120)  # 2 minutes
            # Set offline
            await update_status(client, offline=True)
            await db.update_account(phone, {"is_online": False})
    except Exception as e:
        print(f"Mode 2 monitor error for {phone}: {e}")
    finally:
        await safe_disconnect(client)
