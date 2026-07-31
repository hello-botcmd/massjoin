import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from client_manager import client_manager
from handlers.utils import (
    unhide_last_seen, set_privacy, get_stop_event,
    parse_mode_counts, distribute_accounts
)
from telethon import types, functions

logger = logging.getLogger(__name__)

WAIT_MODE_COUNTS = 1
_online_tasks = {}  # account_id -> asyncio.Task

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def mode_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎭 Send counts as: `mode1, mode2, mode3`\n"
        "Example: `5,3,2`\n\n"
        "*Mode 1* — Always online\n"
        "*Mode 2* — Online 2 min, then offline\n"
        "*Mode 3* — Hidden last seen",
        parse_mode="Markdown"
    )
    return WAIT_MODE_COUNTS

async def mode_counts_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    parsed = parse_mode_counts(update.message.text.strip())
    if not parsed:
        await update.message.reply_text("❌ Invalid. Use e.g.: `5,3,2`", parse_mode="Markdown")
        return WAIT_MODE_COUNTS

    c1, c2, c3 = parsed
    total = c1 + c2 + c3
    accounts = await db.get_active_accounts()

    if len(accounts) < total:
        await update.message.reply_text(
            f"❌ Need {total} active accounts, but only {len(accounts)} available."
        )
        return ConversationHandler.END

    # Stop any existing mode tasks for ALL accounts (to avoid conflicts)
    for acc in accounts:
        await stop_account_mode(acc)

    assignments = distribute_accounts(accounts, (c1, c2, c3))
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

async def stop_account_mode(account):
    """Stop any running online task and disconnect persistent client."""
    account_id = str(account.get("_id", account.get("phone")))
    task = _online_tasks.pop(account_id, None)
    if task:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    # Disconnect persistent client if exists
    try:
        await client_manager.disconnect_client(account_id)
    except Exception:
        pass
    # Also set offline via fresh client as fallback
    try:
        client = await client_manager.get_or_create_client(account.get("session_string"), account_id)
        if client:
            await client(functions.account.UpdateStatusRequest(offline=True))
            await client_manager.disconnect_client(account_id)
    except Exception:
        pass
    await db.update_account(account_id, {
        "current_mode": 0,
        "online_task_running": False,
        "in_use": False
    })

async def apply_mode_to_account(account, mode):
    account_id = str(account.get("_id", account.get("phone")))
    phone = account.get("phone", account_id)
    session_string = account.get("session_string")

    # Stop any previous mode
    await stop_account_mode(account)

    if mode in (1, 2):
        # Get persistent client
        client = await client_manager.get_or_create_client(session_string, account_id)
        if not client:
            await db.update_account(account_id, {"status": "disconnected"})
            return f"❌ {phone}: session invalid"

        # Unhide last seen if previously hidden
        await unhide_last_seen(client)

        # Set online
        try:
            await client(functions.account.UpdateStatusRequest(offline=False))
        except Exception as e:
            return f"❌ {phone}: {e}"

        await db.update_account(account_id, {
            "status": "active",
            "current_mode": mode,
            "online_task_running": True,
            "in_use": True,
            "is_hidden": False,
            "privacy": "normal"
        })

        # Start online loop
        task = asyncio.create_task(_online_loop(account, mode))
        _online_tasks[account_id] = task
        label = "always online" if mode == 1 else "online 2 min"
        return f"✅ {phone}: mode {mode} ({label})"

    elif mode == 3:
        # Hide last seen – use fresh client (no persistent needed)
        client = await client_manager.get_or_create_client(session_string, account_id)
        if not client:
            await db.update_account(account_id, {"status": "disconnected"})
            return f"❌ {phone}: session invalid"
        try:
            await set_privacy(
                client,
                types.InputPrivacyKeyStatusTimestamp(),
                [types.InputPrivacyValueDisallowAll()]
            )
            await client(functions.account.UpdateStatusRequest(offline=False))
            await client_manager.disconnect_client(account_id)
        except Exception as e:
            await client_manager.disconnect_client(account_id)
            return f"❌ {phone}: {e}"
        await db.update_account(account_id, {
            "status": "active",
            "current_mode": 3,
            "online_task_running": False,
            "in_use": False,
            "is_hidden": True,
            "privacy": "hidden"
        })
        return f"✅ {phone}: mode 3 (hidden last seen)"

    return f"❌ {phone}: unknown mode"

async def _online_loop(account, mode):
    account_id = str(account.get("_id", account.get("phone")))
    phone = account.get("phone", account_id)
    try:
        while True:
            # Check stop event for owner
            owner_uid = account.get("owner_uid")
            if owner_uid:
                ev = get_stop_event(owner_uid)
                if ev.is_set():
                    break
            # Get persistent client (should already exist)
            client = await client_manager.get_client(account_id)
            if not client:
                # Try to recreate
                client = await client_manager.get_or_create_client(account.get("session_string"), account_id)
                if not client:
                    await asyncio.sleep(5)
                    continue
            try:
                await client(functions.account.UpdateStatusRequest(offline=False))
                if mode == 2:
                    # Mode 2: online for 2 minutes, then offline
                    await asyncio.sleep(120)
                    await client(functions.account.UpdateStatusRequest(offline=True))
                    await client_manager.disconnect_client(account_id)
                    break
                else:
                    # Mode 1: ping every 25 seconds
                    await asyncio.sleep(25)
            except Exception as e:
                logger.warning(f"Online loop error {phone}: {e}")
                await asyncio.sleep(5)
                # Client may be dead; it will be recreated on next iteration
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Online loop fatal {phone}: {e}")
    finally:
        # Cleanup
        await db.update_account(account_id, {
            "online_task_running": False,
            "in_use": False
        })
        if mode == 2:
            # Ensure offline
            try:
                await client_manager.disconnect_client(account_id)
            except Exception:
                pass
        _online_tasks.pop(account_id, None)
