from telegram import Update
from telegram.ext import ContextTypes
from database import db
from handlers.utils import get_client_for_account, update_status, set_privacy, safe_disconnect
from telethon import types
import asyncio

async def reset_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset profile button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔄 Resetting all account profiles to normal state..."
    )
    
    # Get all accounts
    accounts = await db.get_all_accounts()
    total = len(accounts)
    
    if total == 0:
        await query.edit_message_text(
            "❌ No accounts found in the database."
        )
        return
    
    # Reset all accounts in database
    await db.reset_all_profiles()
    
    # Apply normal status to all accounts
    success_count = 0
    failed_count = 0
    
    for idx, account in enumerate(accounts, 1):
        client = None
        try:
            client = await get_client_for_account(account)
            if client:
                # Update status to online
                await update_status(client, offline=False)
                
                # Reset privacy settings
                await set_privacy(
                    client,
                    types.InputPrivacyKeyStatusTimestamp(),
                    types.InputPrivacyRuleAllowAll()
                )
                
                # Update last seen
                await client(functions.account.UpdateProfileRequest(
                    about=None  # Reset about if needed
                ))
                
                success_count += 1
                await safe_disconnect(client)
                
                # Update progress every 10 accounts
                if idx % 10 == 0:
                    await query.edit_message_text(
                        f"🔄 Resetting profiles...\n"
                        f"Progress: {idx}/{total}\n"
                        f"✅ Success: {success_count}\n"
                        f"❌ Failed: {failed_count}"
                    )
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1
            await safe_disconnect(client)
        
        # Small delay between resets
        await asyncio.sleep(0.5)
    
    await query.edit_message_text(
        f"✅ **Profile Reset Complete!**\n\n"
        f"📊 Total accounts: {total}\n"
        f"✅ Successfully reset: {success_count}\n"
        f"❌ Failed: {failed_count}\n\n"
        f"All accounts are now in normal state with visible last seen."
    )
