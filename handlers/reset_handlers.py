from telegram import Update
from telegram.ext import ContextTypes
from database import db
from handlers.utils import get_fresh_client, reset_profile, safe_disconnect
import asyncio

async def reset_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset all accounts to normal state: show last seen, no hidden mode."""
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
        client = None
        try:
            client = await get_fresh_client(acc.get("session_string"))
            if client:
                ok = await reset_profile(client)
                if ok:
                    success += 1
                else:
                    failed += 1
                await safe_disconnect(client)
            else:
                failed += 1
        except Exception:
            failed += 1
            await safe_disconnect(client)
        await asyncio.sleep(0.5)  # avoid flood

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
        f"All accounts now show last seen normally.",
        parse_mode="Markdown"
    )
