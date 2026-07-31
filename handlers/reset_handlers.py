from telegram import Update
from telegram.ext import ContextTypes
from database import db
from client_manager import client_manager
from handlers.utils import set_last_seen_privacy
from handlers.mode_handlers import stop_account_mode  # kill lingering loops
from telethon import functions
import asyncio
import logging

logger = logging.getLogger(__name__)

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

        # 1) Stop any running mode loop first, or it will reconnect
        try:
            await stop_account_mode(acc)
        except Exception as e:
            logger.warning(f"stop mode {account_id}: {e}")

        # 2) Now reset privacy + go offline on a clean connection.
        client = None
        try:
            client = await client_manager.get_or_create_client(
                acc.get("session_string"), account_id)
            if not client:
                failed += 1
                continue
            if not await set_last_seen_privacy(client, show_last_seen=True):
                raise RuntimeError("setPrivacy failed")
            await client(functions.account.UpdateStatusRequest(offline=True))
            success += 1
        except Exception as e:
            logger.error(f"reset {account_id}: {e}")
            failed += 1
        finally:
            await client_manager.disconnect_client(account_id)
        await asyncio.sleep(0.5)

    # Update DB – align keys with the rest of the codebase
    await db.update_many_accounts({}, {
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
