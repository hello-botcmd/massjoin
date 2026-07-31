import asyncio
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from client_manager import client_manager
from handlers.utils import parse_time_range, safe_disconnect
from telethon import errors

logger = logging.getLogger(__name__)

# Conversation states
(JOIN_LINK, JOIN_COUNT, JOIN_TIMING) = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def join_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔗 **Join Channel/Group**\n\n"
        "Please send the **channel/group link or username**\n"
        "Examples:\n"
        "- `https://t.me/username`\n"
        "- `https://t.me/+abc123`\n"
        "- `@username`\n"
        "- `username`\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return JOIN_LINK

async def join_link_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join link/username"""
    target = update.message.text.strip()
    
    if target.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    context.user_data["join_target"] = target
    
    # Get active accounts
    accounts = await db.get_active_accounts()
    total_accounts = len(accounts)
    
    if total_accounts == 0:
        await update.message.reply_text(
            "❌ No active accounts found. Please add accounts first."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"🔢 How many accounts should join? (1-{total_accounts})\n\n"
        f"Send /cancel to cancel."
    )
    return JOIN_COUNT

async def join_count_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join count"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❌ Send a valid positive number.\n\nSend /cancel to cancel.")
        return JOIN_COUNT
    
    count = int(text)
    accounts = await db.get_active_accounts()
    
    if count > len(accounts):
        await update.message.reply_text(
            f"❌ Only {len(accounts)} active accounts available, but you requested {count}.\n\n"
            f"Please send a number between 1 and {len(accounts)}."
        )
        return JOIN_COUNT
    
    context.user_data["join_count"] = count
    
    await update.message.reply_text(
        "⏱️ **Timing Configuration**\n\n"
        "Send timing *(e.g., `min-1s max-8s`)*:\n\n"
        "Examples:\n"
        "- `min-1s max-8s` (1-8 seconds delay)\n"
        "- `min-2s max-5s` (2-5 seconds delay)\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return JOIN_TIMING

async def join_timing_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join timing and start joining"""
    timing_text = update.message.text.strip()
    
    if timing_text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    min_time, max_time = parse_time_range(timing_text)
    
    if min_time is None or max_time is None or min_time > max_time:
        await update.message.reply_text(
            "❌ Invalid timing. Use e.g.: `min-1s max-8s`\n\n"
            "Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return JOIN_TIMING
    
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
        f"Timing: `{min_time}s` – `{max_time}s` (alternating)\n"
        f"Progress: 0/{count}",
        parse_mode="Markdown",
    )
    
    results = []
    joined_count = 0
    failed_count = 0
    
    for i, account in enumerate(selected):
        client = None
        try:
            # Get client for this account
            session_string = account.get("session_string")
            if not session_string:
                results.append(f"❌ #{i+1} — No session string")
                failed_count += 1
                continue
            
            # Create client
            client = await client_manager.get_or_create_client(session_string, account.get("_id", "unknown"))
            if not client:
                results.append(f"❌ #{i+1} — Failed to connect")
                failed_count += 1
                continue
            
            # Join the target
            success, error_msg = await join_target(client, target)
            
            if success:
                joined_count += 1
                results.append(f"✅ #{i+1} — Joined successfully")
            else:
                failed_count += 1
                results.append(f"❌ #{i+1} — {error_msg}")
            
            await safe_disconnect(client)
            
        except Exception as e:
            failed_count += 1
            results.append(f"❌ #{i+1} — Error: {str(e)[:50]}")
            await safe_disconnect(client)
        
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
        if i < count - 1:
            delay = min_time if i % 2 == 0 else max_time
            await asyncio.sleep(delay)
    
    # Final result
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
    
    # Clean up
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
            return True, None
        except AttributeError:
            # Fallback for older Telethon versions
            await client.join_group(entity)
            return True, None
            
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
