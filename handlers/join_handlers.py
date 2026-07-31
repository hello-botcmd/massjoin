import asyncio
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from database import db
from client_manager import client_manager
from telethon import errors

logger = logging.getLogger(__name__)

# Conversation states
WAIT_JOIN_LINK, WAIT_JOIN_COUNT, WAIT_JOIN_TIMING = range(3)

# Stop events for users
stop_events = {}

def get_stop_event(user_id):
    """Get or create a stop event for a user"""
    if user_id not in stop_events:
        stop_events[user_id] = asyncio.Event()
    return stop_events[user_id]

def clear_stop_event(user_id):
    """Clear the stop event for a user"""
    if user_id in stop_events:
        stop_events[user_id].clear()

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def join_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join button click"""
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
    """Process join link/username"""
    context.user_data["join_target"] = update.message.text.strip()
    await update.message.reply_text(
        "🔢 How many accounts should join?\n\n"
        "Send /cancel to cancel."
    )
    return WAIT_JOIN_COUNT

async def join_count_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join count"""
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
    """Process join timing and start joining"""
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

        client = None
        phone = acc.get("_id", acc.get("phone", "unknown"))
        session_string = acc.get("session_string")
        
        if not session_string:
            results.append(f"❌ #{i+1} — {phone} no session string")
            failed_count += 1
            continue
        
        try:
            # Get client
            client = await client_manager.get_or_create_client(session_string, phone)
            if not client:
                results.append(f"❌ #{i+1} — {phone} failed to connect")
                failed_count += 1
                continue

            # Join the target
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
            if client:
                try:
                    await client.disconnect()
                except:
                    pass

        # Update progress every 5 accounts or at the end
        if (i + 1) % 5 == 0 or i == count - 1:
            try:
                await status_msg.edit_text(
                    f"⏳ Joining... ({i+1}/{count})\n"
                    f"✅ Joined: {joined_count}\n"
                    f"❌ Failed: {failed_count}\n\n"
                    f"```\n" + "\n".join(results[-10:]) + "\n```",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to update status: {e}")

        # Random delay between joins (alternating min/max)
        delay = min_s if i % 2 == 0 else max_s
        if i < count - 1 and not stop_ev.is_set():
            await asyncio.sleep(delay)

    clear_stop_event(uid)
    summary = "\n".join(results)
    
    final_message = (
        f"🔗 **Join Results**\n\n"
        f"📌 Target: {target}\n"
        f"📊 Total: {count}\n"
        f"✅ Joined: {joined_count}\n"
        f"❌ Failed: {failed_count}\n\n"
        f"```\n{summary[:3000]}\n```"
    )
    
    await status_msg.edit_text(
        final_message,
        parse_mode="Markdown"
    )

    for k in ["join_target", "join_count"]:
        context.user_data.pop(k, None)
    return ConversationHandler.END

async def join_target(client, target):
    """Join a channel/group"""
    try:
        # Clean up the target
        if 'https://t.me/' in target:
            target = target.split('https://t.me/')[-1]
        elif 't.me/' in target:
            target = target.split('t.me/')[-1]
        
        if target.startswith('@'):
            target = target[1:]
        
        # Get the entity
        entity = await client.get_entity(target)
        
        # Try to join
        try:
            await client.join_channel(entity)
            return True, "Success"
        except AttributeError:
            # Fallback for older Telethon versions
            await client.join_group(entity)
            return True, "Success"
            
    except errors.rpcerrorlist.ChannelInvalidError:
        return False, "Invalid channel or group"
    except errors.rpcerrorlist.ChannelPrivateError:
        return False, "Channel is private or doesn't exist"
    except errors.rpcerrorlist.UserAlreadyParticipantError:
        return False, "Already a participant"
    except errors.rpcerrorlist.FloodWaitError as e:
        return False, f"Rate limited. Wait {e.seconds}s"
    except ValueError as e:
        return False, f"Invalid target: {str(e)[:50]}"
    except Exception as e:
        return False, str(e)[:100]

def parse_timing(timing_str):
    """Parse timing string like 'min-1s max-8s' or '2 6'"""
    import re
    try:
        min_time = None
        max_time = None
        
        # Try format: min-1s max-8s
        min_match = re.search(r'min-(\d+)([sm]?)', timing_str)
        if min_match:
            value = int(min_match.group(1))
            unit = min_match.group(2)
            min_time = value if unit == 's' else value * 60
        
        max_match = re.search(r'max-(\d+)([sm]?)', timing_str)
        if max_match:
            value = int(max_match.group(1))
            unit = max_match.group(2)
            max_time = value if unit == 's' else value * 60
        
        # Try simple format like "2 6"
        if min_time is None and max_time is None:
            parts = timing_str.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                min_time = int(parts[0])
                max_time = int(parts[1])
        
        if min_time is not None and max_time is not None and min_time <= max_time:
            return (min_time, max_time)
        return None
    except Exception:
        return None
