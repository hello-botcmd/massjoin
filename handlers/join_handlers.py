import asyncio
import logging
import random
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import db
from client_manager import client_manager
from handlers.utils import join_target, get_stop_event, clear_stop_event, parse_timing

logger = logging.getLogger(__name__)

# States
WAIT_JOIN_LINK, WAIT_JOIN_COUNT, WAIT_JOIN_TIMING = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def join_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for join"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔗 Send the channel/group **username** or **invite link**:\n\n"
        "Examples:\n"
        "- `https://t.me/username`\n"
        "- `https://t.me/+abc123`\n"
        "- `@username`\n"
        "- `username`\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return WAIT_JOIN_LINK

async def join_link_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join link"""
    context.user_data["join_target"] = update.message.text.strip()
    await update.message.reply_text(
        "🔢 How many accounts should join?\n\nSend /cancel to cancel."
    )
    return WAIT_JOIN_COUNT

async def join_count_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join count"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❌ Send a valid positive number.\n\nSend /cancel to cancel.")
        return WAIT_JOIN_COUNT
    
    context.user_data["join_count"] = int(text)
    await update.message.reply_text(
        "⏱️ Send timing *(e.g., `min-1s max-8s` or `2 6`)*:\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return WAIT_JOIN_TIMING

async def join_timing_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join timing and execute"""
    uid = update.effective_user.id
    timing_text = update.message.text.strip()
    
    if timing_text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    timing = parse_timing(timing_text)
    if not timing:
        await update.message.reply_text(
            "❌ Invalid timing. Use e.g.: `min-1s max-8s`\n\n"
            "Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return WAIT_JOIN_TIMING

    min_s, max_s = timing
    target = context.user_data["join_target"]
    count = context.user_data["join_count"]
    accounts = await db.get_active_accounts()

    if len(accounts) < count:
        await update.message.reply_text(
            f"❌ Only {len(accounts)} active, but {count} requested.",
        )
        for k in ["join_target", "join_count"]:
            context.user_data.pop(k, None)
        return ConversationHandler.END

    selected = random.sample(accounts, count)
    status_msg = await update.message.reply_text(
        f"⏳ Joining {target} with {count} accounts...\n"
        f"Timing: `{min_s}s` – `{max_s}s` (alternating)",
        parse_mode="Markdown",
    )

    stop_ev = get_stop_event(uid)
    results = []
    joined_count = 0
    failed_count = 0
    
    for i, acc in enumerate(selected):
        if stop_ev.is_set():
            results.append(f"⏹️ #{i+1} — stopped by user")
            break

        phone = acc.get("_id", acc.get("phone", "unknown"))
        session_string = acc.get("session_string")
        
        if not session_string:
            results.append(f"❌ #{i+1} — {phone} no session string")
            failed_count += 1
            continue
        
        try:
            client = await client_manager.get_or_create_client(session_string, phone)
            if not client:
                results.append(f"❌ #{i+1} — {phone} failed to connect")
                failed_count += 1
                continue

            ok, msg = await join_target(client, target)
            status = "✅" if ok else "❌"
            if ok:
                joined_count += 1
            else:
                failed_count += 1
            results.append(f"{status} #{i+1} — {phone} — {msg}")
            
            await client_manager.disconnect_client(phone)
            
        except Exception as e:
            failed_count += 1
            results.append(f"❌ #{i+1} — {phone} — Error: {str(e)[:50]}")

        if (i + 1) % 5 == 0 or i == count - 1:
            try:
                await status_msg.edit_text(
                    f"⏳ Joining... ({i+1}/{count})\n"
                    f"✅ Joined: {joined_count}\n"
                    f"❌ Failed: {failed_count}\n\n"
                    f"```\n" + "\n".join(results[-10:]) + "\n```",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        delay = min_s if i % 2 == 0 else max_s
        if i < count - 1 and not stop_ev.is_set():
            await asyncio.sleep(delay)

    clear_stop_event(uid)
    summary = "\n".join(results)
    await status_msg.edit_text(
        f"🔗 **Join Results**\n\n"
        f"📌 Target: {target}\n"
        f"📊 Total: {count}\n"
        f"✅ Joined: {joined_count}\n"
        f"❌ Failed: {failed_count}\n\n"
        f"```\n{summary[:3000]}\n```",
        parse_mode="Markdown"
    )

    for k in ["join_target", "join_count"]:
        context.user_data.pop(k, None)
    return ConversationHandler.END
