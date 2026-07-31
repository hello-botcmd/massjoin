from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_fresh_client, safe_disconnect
from telethon import functions, types
import asyncio
import random

REACTION_LINK, REACTION_COUNT, REACTION_TYPES = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def reaction_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎯 Send the **post link** to add reactions:\n"
        "Example: `https://t.me/username/123`\n\nSend /cancel to cancel.",
        parse_mode="Markdown"
    )
    return REACTION_LINK

async def reaction_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reaction_link"] = update.message.text.strip()
    await update.message.reply_text("🔢 How many reactions to add?\n\nSend /cancel to cancel.")
    return REACTION_COUNT

async def reaction_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❌ Send a positive number.")
        return REACTION_COUNT
    context.user_data["reaction_count"] = int(text)
    await update.message.reply_text(
        "🎭 Send reactions (emoji(s) separated by space):\n"
        "Example: `❤️ 🥰 😍`\n\nSend /cancel to cancel."
    )
    return REACTION_TYPES

async def reaction_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
    reactions = text.split()
    if not reactions:
        await update.message.reply_text("❌ Send at least one emoji.")
        return REACTION_TYPES
    context.user_data["reaction_types"] = reactions

    link = context.user_data["reaction_link"]
    count = context.user_data["reaction_count"]
    await update.message.reply_text(f"⏳ Adding {count} reactions to {link}...")

    accounts = await db.get_active_accounts()
    selected = random.sample(accounts, min(count, len(accounts)))
    status_msg = await update.message.reply_text(f"Progress: 0/{len(selected)}")

    success = 0
    failed = 0
    for i, acc in enumerate(selected):
        client = None
        try:
            client = await get_fresh_client(acc.get("session_string"))
            if not client:
                failed += 1
                continue
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
                failed += 1
                continue
            entity = await client.get_entity(channel)
            reaction = random.choice(reactions)
            await client(functions.messages.SendReactionRequest(
                peer=entity,
                msg_id=msg_id,
                reaction=[types.ReactionEmoji(emoticon=reaction)]
            ))
            success += 1
        except Exception:
            failed += 1
        finally:
            await safe_disconnect(client)
        if (i+1) % 5 == 0 or i == len(selected)-1:
            await status_msg.edit_text(
                f"Progress: {i+1}/{len(selected)}\n✅ Success: {success}\n❌ Failed: {failed}"
            )
        await asyncio.sleep(1)

    await status_msg.edit_text(
        f"✅ **Reaction Complete**\n\n"
        f"📌 Target: {link}\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"🎯 Reactions: {' '.join(reactions)}",
        parse_mode="Markdown"
    )
    for k in ["reaction_link", "reaction_count", "reaction_types"]:
        context.user_data.pop(k, None)
    return ConversationHandler.END
