from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_client_for_account, random_delay, safe_disconnect
from telethon import functions, types
import asyncio
import random

# Conversation states
(REACTION_LINK, REACTION_COUNT, REACTION_TYPES) = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text(
        "❌ Operation cancelled."
    )
    return ConversationHandler.END

async def reaction_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reaction button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎯 **Reaction Configuration**\n\n"
        "Please send the **post link** to add reactions to.\n"
        "Format: `https://t.me/username/post_id`",
        parse_mode="Markdown"
    )
    return REACTION_LINK

async def reaction_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process reaction link"""
    link = update.message.text.strip()
    context.user_data['reaction_link'] = link
    
    accounts = await db.get_active_accounts()
    total = len(accounts)
    
    if total == 0:
        await update.message.reply_text(
            "❌ No active accounts found."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📊 **Reaction Configuration**\n\n"
        f"📌 Target: {link}\n"
        f"👤 Available accounts: {total}\n\n"
        f"How many reactions should be added?\n"
        f"Please send a number (1-{total}):",
        parse_mode="Markdown"
    )
    return REACTION_COUNT

async def reaction_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process reaction count"""
    try:
        count = int(update.message.text.strip())
        accounts = await db.get_active_accounts()
        
        if count < 1 or count > len(accounts):
            await update.message.reply_text(
                f"❌ Please send a number between 1 and {len(accounts)}."
            )
            return REACTION_COUNT
        
        context.user_data['reaction_count'] = count
        
        await update.message.reply_text(
            f"🎯 **Reaction Configuration**\n\n"
            f"Please send the **reaction emojis** to add.\n"
            f"You can send multiple emojis separated by spaces.\n\n"
            f"Examples:\n"
            f"- `❤️`\n"
            f"- `❤️ 🥰`\n"
            f"- `❤️ 🥰 😍`",
            parse_mode="Markdown"
        )
        return REACTION_TYPES
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number."
        )
        return REACTION_COUNT

async def reaction_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process reaction types and start adding reactions"""
    reactions = update.message.text.strip().split()
    
    if not reactions:
        await update.message.reply_text(
            "❌ Please send at least one reaction emoji."
        )
        return REACTION_TYPES
    
    context.user_data['reaction_types'] = reactions
    
    link = context.user_data['reaction_link']
    count = context.user_data['reaction_count']
    
    await update.message.reply_text(
        f"🔄 Adding {count} reactions to {link}\n"
        f"Reactions: {' '.join(reactions)}\n\n"
        f"Starting process..."
    )
    
    await start_reaction_process(update, context)
    return ConversationHandler.END

async def start_reaction_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the reaction process"""
    link = context.user_data['reaction_link']
    count = context.user_data['reaction_count']
    reactions = context.user_data['reaction_types']
    
    accounts = await db.get_active_accounts()
    selected_accounts = random.sample(accounts, min(count, len(accounts)))
    
    status_msg = await update.message.reply_text(
        f"🔄 Adding reactions...\n"
        f"Progress: 0/{len(selected_accounts)}"
    )
    
    success_count = 0
    failed_count = 0
    
    for idx, account in enumerate(selected_accounts, 1):
        client = None
        try:
            client = await get_client_for_account(account)
            if client:
                # Get the message entity
                entity = await client.get_entity(link)
                message_id = int(link.split('/')[-1])
                
                # Choose a random reaction for each account
                reaction = random.choice(reactions)
                
                # Add reaction
                await client(functions.messages.SendReactionRequest(
                    peer=entity,
                    msg_id=message_id,
                    reaction=[types.ReactionEmoji(emoticon=reaction)]
                ))
                
                success_count += 1
                await status_msg.edit_text(
                    f"✅ Added {reaction}\n"
                    f"Progress: {idx}/{len(selected_accounts)}\n"
                    f"✅ Success: {success_count}\n"
                    f"❌ Failed: {failed_count}"
                )
                
                await safe_disconnect(client)
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1
            await safe_disconnect(client)
        
        # 1 second delay between reactions
        if idx < len(selected_accounts):
            await asyncio.sleep(1)
    
    await status_msg.edit_text(
        f"✅ **Reaction Process Complete!**\n\n"
        f"📌 Target: {link}\n"
        f"📊 Total: {len(selected_accounts)}\n"
        f"✅ Success: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"🎯 Reactions: {' '.join(reactions)}"
    )
