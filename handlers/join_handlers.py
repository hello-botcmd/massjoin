from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_client_for_account, join_channel, random_delay, parse_time_range, safe_disconnect
import asyncio
import random

# Conversation states
(JOIN_LINK, JOIN_COUNT, JOIN_TIMING, JOIN_CONFIRM) = range(4)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text(
        "❌ Operation cancelled."
    )
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
        "- `@username`\n"
        "- `username`",
        parse_mode="Markdown"
    )
    return JOIN_LINK

async def join_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join link/username"""
    link = update.message.text.strip()
    context.user_data['join_link'] = link
    
    # Get active accounts
    accounts = await db.get_active_accounts()
    total_accounts = len(accounts)
    
    if total_accounts == 0:
        await update.message.reply_text(
            "❌ No active accounts found. Please add accounts first."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📊 **Join Configuration**\n\n"
        f"📌 Target: {link}\n"
        f"👤 Available accounts: {total_accounts}\n\n"
        f"How many accounts should join?\n"
        f"Please send a number (1-{total_accounts}):",
        parse_mode="Markdown"
    )
    return JOIN_COUNT

async def join_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join count"""
    try:
        count = int(update.message.text.strip())
        accounts = await db.get_active_accounts()
        
        if count < 1 or count > len(accounts):
            await update.message.reply_text(
                f"❌ Please send a number between 1 and {len(accounts)}."
            )
            return JOIN_COUNT
        
        context.user_data['join_count'] = count
        
        await update.message.reply_text(
            f"⏱️ **Timing Configuration**\n\n"
            f"Please specify the delay between joins.\n"
            f"Format: `min-Xs max-Ys`\n\n"
            f"Examples:\n"
            f"- `min-1s max-8s` (1-8 seconds delay)\n"
            f"- `min-2s max-5s` (2-5 seconds delay)\n"
            f"- `min-500ms max-2s` (0.5-2 seconds delay)",
            parse_mode="Markdown"
        )
        return JOIN_TIMING
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number."
        )
        return JOIN_COUNT

async def join_timing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process join timing"""
    timing = update.message.text.strip()
    min_time, max_time = parse_time_range(timing)
    
    if min_time is None or max_time is None or min_time > max_time:
        await update.message.reply_text(
            "❌ Invalid timing format. Please use:\n"
            "`min-1s max-8s`\n\n"
            "Make sure min time is less than max time.",
            parse_mode="Markdown"
        )
        return JOIN_TIMING
    
    context.user_data['join_min_time'] = min_time
    context.user_data['join_max_time'] = max_time
    
    # Show confirmation and start joining
    await update.message.reply_text(
        f"✅ **Join Configuration Complete**\n\n"
        f"📌 Target: {context.user_data['join_link']}\n"
        f"👤 Accounts: {context.user_data['join_count']}\n"
        f"⏱️ Timing: {min_time}-{max_time} seconds\n\n"
        f"🔄 Starting join process..."
    )
    
    await start_join_process(update, context)
    return ConversationHandler.END

async def start_join_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the join process"""
    link = context.user_data['join_link']
    count = context.user_data['join_count']
    min_time = context.user_data['join_min_time']
    max_time = context.user_data['join_max_time']
    
    # Get active accounts
    accounts = await db.get_active_accounts()
    selected_accounts = random.sample(accounts, min(count, len(accounts)))
    
    # Update status message
    status_msg = await update.message.reply_text(
        f"🔄 Joining accounts to {link}...\n"
        f"Progress: 0/{len(selected_accounts)}"
    )
    
    joined_count = 0
    failed_count = 0
    
    for idx, account in enumerate(selected_accounts, 1):
        client = None
        try:
            client = await get_client_for_account(account)
            if client:
                success, error = await join_channel(client, link)
                if success:
                    joined_count += 1
                    await status_msg.edit_text(
                        f"✅ Joined {link}\n"
                        f"Progress: {idx}/{len(selected_accounts)}\n"
                        f"✅ Joined: {joined_count}\n"
                        f"❌ Failed: {failed_count}"
                    )
                else:
                    failed_count += 1
                    await status_msg.edit_text(
                        f"❌ Failed to join {link}\n"
                        f"Error: {error}\n"
                        f"Progress: {idx}/{len(selected_accounts)}\n"
                        f"✅ Joined: {joined_count}\n"
                        f"❌ Failed: {failed_count}"
                    )
                
                await safe_disconnect(client)
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1
            await safe_disconnect(client)
        
        # Random delay between joins
        if idx < len(selected_accounts):
            delay = random.uniform(min_time, max_time)
            await asyncio.sleep(delay)
    
    await status_msg.edit_text(
        f"✅ **Join Process Complete!**\n\n"
        f"📌 Target: {link}\n"
        f"📊 Total: {len(selected_accounts)}\n"
        f"✅ Joined: {joined_count}\n"
        f"❌ Failed: {failed_count}"
    )
