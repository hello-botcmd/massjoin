from telegram import Update
from telegram.ext import ContextTypes
from database import db
from handlers.utils import get_client_for_account, update_status, safe_disconnect
import asyncio

async def online_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all accounts online button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔄 Bringing all accounts online..."
    )
    
    # Get all accounts
    accounts = await db.get_all_accounts()
    total = len(accounts)
    
    if total == 0:
        await query.edit_message_text(
            "❌ No accounts found in the database."
        )
        return
    
    # Set all accounts to mode 1 (always online)
    await db.update_many_accounts(
        {},
        {"mode": "mode1", "privacy": "normal", "is_hidden": False}
    )
    
    # Bring all accounts online
    success_count = 0
    failed_count = 0
    
    for idx, account in enumerate(accounts, 1):
        client = None
        try:
            client = await get_client_for_account(account)
            if client:
                await update_status(client, offline=False)
                success_count += 1
                await safe_disconnect(client)
            else:
                failed_count += 1
        except Exception:
            failed_count += 1
            await safe_disconnect(client)
        
        # Update progress every 10 accounts
        if idx % 10 == 0:
            await query.edit_message_text(
                f"🔄 Bringing accounts online...\n"
                f"Progress: {idx}/{total}\n"
                f"✅ Success: {success_count}\n"
                f"❌ Failed: {failed_count}"
            )
        
        await asyncio.sleep(0.5)
    
    await query.edit_message_text(
        f"✅ **All Accounts Online!**\n\n"
        f"📊 Total accounts: {total}\n"
        f"✅ Successfully online: {success_count}\n"
        f"❌ Failed: {failed_count}\n\n"
        f"All accounts are now in Mode 1 (Always Online)."
    )
