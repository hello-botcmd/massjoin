from telegram import Update
from telegram.ext import ContextTypes
from database import db
from handlers.utils import get_fresh_client, update_status, safe_disconnect
import asyncio

async def online_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bring all accounts online (mode 1)"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🟢 Bringing all accounts online...")

    accounts = await db.get_all_accounts()
    if not accounts:
        await query.edit_message_text("❌ No accounts found.")
        return

    success = 0
    failed = 0
    for acc in accounts:
        client = None
        try:
            client = await get_fresh_client(acc.get("session_string"))
            if client:
                await update_status(client, offline=False)
                success += 1
                await safe_disconnect(client)
            else:
                failed += 1
        except Exception:
            failed += 1
            await safe_disconnect(client)
        await asyncio.sleep(0.5)

    # Update database: set mode to mode1 and clear hidden flags
    await db.update_many_accounts({}, {
        "mode": "mode1",
        "current_mode": 1,
        "is_hidden": False,
        "privacy": "normal",
        "online_task_running": True
    })

    await query.edit_message_text(
        f"✅ **All Accounts Online**\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"All accounts are now online (Mode 1).",
        parse_mode="Markdown"
    )
