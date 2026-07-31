from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_fresh_client, safe_disconnect
from telethon import functions
import asyncio
import random

VIEWS_LINK, VIEWS_COUNT = range(2)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def views_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👁️ Send the **post link(s)** (one per line):\n"
        "Example:\n"
        "https://t.me/username/123\n"
        "https://t.me/username/456\n\nSend /cancel to cancel.",
        parse_mode="Markdown"
    )
    return VIEWS_LINK

async def views_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    links = [l.strip() for l in update.message.text.split('\n') if l.strip()]
    if not links:
        await update.message.reply_text("❌ Send at least one link.")
        return VIEWS_LINK
    context.user_data["views_links"] = links
    await update.message.reply_text("🔢 How many views per post?\n\nSend /cancel to cancel.")
    return VIEWS_COUNT

async def views_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❌ Send a positive number.")
        return VIEWS_COUNT
    count = int(text)
    context.user_data["views_count"] = count

    links = context.user_data["views_links"]
    await update.message.reply_text(f"⏳ Boosting views on {len(links)} posts with {count} views each...")

    accounts = await db.get_active_accounts()
    selected = random.sample(accounts, min(count, len(accounts)))
    total_views = len(selected) * len(links)
    status_msg = await update.message.reply_text(f"Progress: 0/{total_views}")

    success = 0
    failed = 0
    current = 0
    for link in links:
        # parse link
        parts = link.split('/')
        if 't.me' in link:
            idx = parts.index('t.me') if 't.me' in parts else parts.index('https:') + 2
            channel = parts[idx+1] if len(parts) > idx+1 else None
            msg_id = int(parts[idx+2]) if len(parts) > idx+2 else None
        else:
            channel = parts[0]
            msg_id = int(parts[1]) if len(parts) > 1 else None
        if not channel or not msg_id:
            failed += len(selected)
            continue
        for acc in selected:
            client = None
            try:
                client = await get_fresh_client(acc.get("session_string"))
                if not client:
                    failed += 1
                    continue
                entity = await client.get_entity(channel)
                await client(functions.messages.GetMessagesViewsRequest(
                    peer=entity,
                    id=[msg_id],
                    increment=True
                ))
                success += 1
            except Exception:
                failed += 1
            finally:
                await safe_disconnect(client)
            current += 1
            if current % 5 == 0 or current == total_views:
                await status_msg.edit_text(
                    f"Progress: {current}/{total_views}\n✅ Success: {success}\n❌ Failed: {failed}"
                )
            await asyncio.sleep(1)

    await status_msg.edit_text(
        f"✅ **Views Boost Complete**\n\n"
        f"📌 Posts: {len(links)}\n"
        f"👁️ Views per post: {count}\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode="Markdown"
    )
    for k in ["views_links", "views_count"]:
        context.user_data.pop(k, None)
    return ConversationHandler.END
