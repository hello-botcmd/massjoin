import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from handlers.utils import (
    get_client_for_account, safe_disconnect, update_status, set_privacy,
    stop_account_mode
)
from telethon import types

logger = logging.getLogger(__name__)

async def reset_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset profile button click"""
    query = update.callback_query
    await query.answer()
    
    status_msg = await query.edit_message_text(
        "🔄 Resetting all account profiles to normal state..."
    )
    
    accounts = await db.get_all_accounts()
    total = len(accounts)
    
    if total == 0:
        await status_msg.edit_text("❌ No accounts found in the database.")
        return
    
    # Reset all accounts in database
    await db.reset_all_profiles()
    
    # Apply normal state to all accounts
    success_count = 0
    failed_count = 0
    
    for idx, account in enumerate(accounts, 1):
        phone = account.get("_id", "unknown")
        try:
            # Stop any ongoing mode tasks
            await stop_account_mode(account)
            
            client = await get_client_for_account(account)
            if client:
                # Set online
                await update_status(client, offline=False)
                
                # Reset privacy to normal (show last seen)
                await set_privacy(
                    client,
                    types.InputPrivacyKeyStatusTimestamp(),
                    types.InputPrivacyValueAllowAll()
                )
                
                # Update database
                await db.update_account(phone, {
                    "mode": "normal",
                    "privacy": "normal",
                    "is_hidden": False,
                    "is_online": True,
                    "current_mode": 0,
                    "online_task_running": False
                })
                
                success_count += 1
                await safe_disconnect(client)
            else:
                failed_count += 1
                logger.warning(f"Could not connect to account {phone}")
        except Exception as e:
            failed_count += 1
            logger.error(f"Error resetting account {phone}: {e}")
        
        # Update progress every 10 accounts
        if idx % 10 == 0:
            await status_msg.edit_text(
                f"🔄 Resetting profiles...\n"
                f"Progress: {idx}/{total}\n"
                f"✅ Success: {success_count}\n"
                f"❌ Failed: {failed_count}"
            )
        
        await asyncio.sleep(0.5)
    
    await status_msg.edit_text(
        f"✅ **Profile Reset Complete!**\n\n"
        f"📊 Total accounts: {total}\n"
        f"✅ Successfully reset: {success_count}\n"
        f"❌ Failed: {failed_count}\n\n"
        f"All accounts are now in normal state with visible last seen."
    )
