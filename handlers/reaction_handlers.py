from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_client_for_account, safe_disconnect
from telethon import functions, types
import asyncio
import random

# Conversation states
(REACTION_LINK, REACTION_COUNT, REACTION_TYPES) = range(3)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def reaction_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reaction button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎯 **Reaction Configuration**\n\n"
        "Please send the **post link** to add reactions to.\n"
        "Format: `https://t.me/username/post_id`\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return REACTION_LINK

async def reaction_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process reaction link"""
    link = update.message.text.strip()
    
    if link.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    context.user_data['reaction_link'] = link
    
    accounts = await db.get_active_accounts()
    total = len(accounts)
    
    if total == 0:
        await update.message.reply_text("❌ No active accounts found.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📊 **Reaction Configuration**\n\n"
        f"📌 Target: {link}\n"
        f"👤 Available accounts: {total}\n\n"
        f"How many reactions should be added?\n"
        f"Please send a number (1-{total}):\n\n"
        f"Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return REACTION_COUNT

async def reaction_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process reaction count"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    try:
        count = int(text)
        accounts = await db.get_active_accounts()
        
        if count < 1 or count > len(accounts):
            await update.message.reply_text(
                f"❌ Please send a number between 1 and {len(accounts)}.\n\n"
                f"Send /cancel to cancel."
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
            f"- `❤️ 🥰 😍`\n\n"
            f"Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        return REACTION_TYPES
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number.\n\n"
            f"Send /cancel to cancel."
        )
        return REACTION_COUNT

async def reaction_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process reaction types and start adding reactions"""
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    reactions = text.split()
    
    if not reactions:
        await update.message.reply_text(
            "❌ Please send at least one reaction emoji.\n\n"
            f"Send /cancel to cancel."
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
            session_string = account.get("session_string")
            if not session_string:
                failed_count += 1
                continue
            
            client = await get_client_for_account(account)
            if client:
                # Get the message entity
                try:
                    # Extract channel username and message ID from link
                    if 'https://t.me/' in link:
                        parts = link.split('https://t.me/')[-1].split('/')
                        channel = parts[0]
                        message_id = int(parts[1]) if len(parts) > 1 else None
                    else:
                        # Assume it's just a username/message_id format
                        parts = link.split('/')
                        channel = parts[0]
                        message_id = int(parts[1]) if len(parts) > 1 else None
                    
                    if not message_id:
                        failed_count += 1
                        continue
                    
                    entity = await client.get_entity(channel)
                    
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
                except Exception as e:
                    failed_count += 1
                    await status_msg.edit_text(
                        f"❌ Error: {str(e)[:50]}\n"
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
    
    # Clean up
    for key in ['reaction_link', 'reaction_count', 'reaction_types']:
        context.user_data.pop(key, None)
