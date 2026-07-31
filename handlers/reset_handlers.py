from telegram import Update
from telegram.ext import ContextTypes
from database import db
from client_manager import client_manager
from handlers.utils import set_privacy_allow_all
from telethon import functions
import asyncio

async def reset_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 Resetting all profiles to normal state...")

    accounts = await db.get_all_accounts()
    if not accounts:
        await query.edit_message_text("❌ No accounts found.")
        return

    success = 0
    failed = 0
    for acc in accounts:
        account_id = str(acc.get("_id", acc.get("phone")))
        session = acc.get("session_string")
        client = None
        try:
            client = await client_manager.get_or_create_client(session, account_id)
            if client:
                # Unhide last seen (allow all)
                await set_privacy_allow_all(client)
                # Set offline
                await client(functions.account.UpdateStatusRequest(offline=True))
                success += 1
                await client_manager.disconnect_client(account_id)
            else:
                failed += 1
        except Exception:
            failed += 1
            await client_manager.disconnect_client(account_id)
        await asyncio.sleep(0.5)

    # Update database: remove mode and hidden flags
    await db.update_many_accounts({}, {
        "mode": "normal",
        "current_mode": 0,
        "is_hidden": False,
        "privacy": "normal",
        "online_task_running": False,
        "in_use": False
    })

    await query.edit_message_text(
        f"✅ **Reset Complete**\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"All accounts now show last seen normally and are offline.",
        parse_mode="Markdown"
    )
