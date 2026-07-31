from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from handlers.utils import get_client_for_account, safe_disconnect
import asyncio
import random
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing conversation"""
    await update.message.reply_text(
        "❌ Operation cancelled."
    )
    return ConversationHandler.END

# Conversation states
(VIEWS_LINK, VIEWS_COUNT) = range(2)

async def views_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle views button click"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "👁️ **Views Configuration**\n\n"
        "Please send the **post link(s)** to boost views.\n"
        "You can send multiple links separated by new lines.\n\n"
        "Format: `https://t.me/username/post_id`",
        parse_mode="Markdown"
    )
    return VIEWS_LINK

async def views_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process views links"""
    links = update.message.text.strip().split('\n')
    links = [link.strip() for link in links if link.strip()]
    
    if not links:
        await update.message.reply_text(
            "❌ Please send at least one valid link."
        )
        return VIEWS_LINK
    
    context.user_data['views_links'] = links
    
    accounts = await db.get_active_accounts()
    total = len(accounts)
    
    if total == 0:
        await update.message.reply_text(
            "❌ No active accounts found."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📊 **Views Configuration**\n\n"
        f"📌 Posts to boost: {len(links)}\n"
        f"👤 Available accounts: {total}\n\n"
        f"How many views should be added to each post?\n"
        f"Please send a number (1-{total}):",
        parse_mode="Markdown"
    )
    return VIEWS_COUNT

async def views_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process views count and start boosting"""
    try:
        count = int(update.message.text.strip())
        accounts = await db.get_active_accounts()
        links = context.user_data['views_links']
        
        if count < 1 or count > len(accounts):
            await update.message.reply_text(
                f"❌ Please send a number between 1 and {len(accounts)}."
            )
            return VIEWS_COUNT
        
        context.user_data['views_count'] = count
        
        await update.message.reply_text(
            f"🔄 Boosting views for {len(links)} posts...\n"
            f"Views per post: {count}\n\n"
            f"Starting process..."
        )
        
        await start_views_process(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Please send a valid number."
        )
        return VIEWS_COUNT

async def start_views_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the views boosting process"""
    links = context.user_data['views_links']
    views_per_post = context.user_data['views_count']
    
    accounts = await db.get_active_accounts()
    selected_accounts = random.sample(accounts, min(views_per_post, len(accounts)))
    
    total_views = len(selected_accounts) * len(links)
    
    status_msg = await update.message.reply_text(
        f"🔄 Boosting views...\n"
        f"Total views to add: {total_views}\n"
        f"Progress: 0/{total_views}"
    )
    
    total_success = 0
    total_failed = 0
    current_view = 0
    
    for link in links:
        # Get the message entity
        try:
            # Test with first account to get entity
            test_client = await get_client_for_account(selected_accounts[0])
            if not test_client:
                await status_msg.edit_text(
                    f"❌ Failed to get entity for {link}\n"
                    f"Please check the link format."
                )
                return
            
            entity = await test_client.get_entity(link)
            message_id = int(link.split('/')[-1])
            await safe_disconnect(test_client)
        except Exception as e:
            await status_msg.edit_text(
                f"❌ Invalid link: {link}\n"
                f"Error: {str(e)}"
            )
            continue
        
        # Add views for this post
        for account in selected_accounts:
            client = None
            try:
                client = await get_client_for_account(account)
                if client:
                    # View the message
                    await client(functions.messages.GetMessagesViewsRequest(
                        peer=entity,
                        id=[message_id],
                        increment=True
                    ))
                    
                    total_success += 1
                    current_view += 1
                    
                    await status_msg.edit_text(
                        f"✅ View added\n"
                        f"Total views: {total_success}/{total_views}\n"
                        f"✅ Success: {total_success}\n"
                        f"❌ Failed: {total_failed}"
                    )
                    
                    await safe_disconnect(client)
                else:
                    total_failed += 1
                    current_view += 1
            except Exception as e:
                total_failed += 1
                current_view += 1
                await safe_disconnect(client)
            
            # 1 second delay between views
            if current_view < total_views:
                await asyncio.sleep(1)
    
    await status_msg.edit_text(
        f"✅ **Views Boost Complete!**\n\n"
        f"📌 Posts boosted: {len(links)}\n"
        f"👁️ Views per post: {views_per_post}\n"
        f"📊 Total views added: {total_success}\n"
        f"✅ Success: {total_success}\n"
        f"❌ Failed: {total_failed}"
    )
