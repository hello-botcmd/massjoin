from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH
import asyncio
import random
import re

async def login_account(session_string, phone=None):
    """Login to Telegram using session string"""
    client = None
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            await client.disconnect()
            return True, me
        else:
            await client.disconnect()
            return False, None
    except Exception as e:
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return False, None

async def join_channel(client, channel_username):
    """Join a channel/group using the correct Telethon method"""
    try:
        # Clean up the channel username/link
        if 'https://t.me/' in channel_username:
            channel_username = channel_username.split('https://t.me/')[-1]
        elif 't.me/' in channel_username:
            channel_username = channel_username.split('t.me/')[-1]
        
        # Remove @ if present
        if channel_username.startswith('@'):
            channel_username = channel_username[1:]
        
        # Get the entity
        entity = await client.get_entity(channel_username)
        
        # Join using the correct method
        # For channels, use join_channel
        # For groups, use join_group (which also works for channels)
        try:
            await client.join_channel(entity)
        except AttributeError:
            # If join_channel doesn't exist, try join_group
            await client.join_group(entity)
        
        return True, None
    except errors.rpcerrorlist.ChannelInvalidError:
        return False, "Invalid channel or group"
    except errors.rpcerrorlist.ChannelPrivateError:
        return False, "Channel is private or doesn't exist"
    except errors.rpcerrorlist.UserAlreadyParticipantError:
        return False, "Already a participant"
    except errors.rpcerrorlist.FloodWaitError as e:
        return False, f"Rate limited. Wait {e.seconds} seconds"
    except Exception as e:
        return False, str(e)

async def leave_channel(client, chat_id):
    """Leave a channel/group"""
    try:
        entity = await client.get_entity(int(chat_id) if chat_id.isdigit() else chat_id)
        await client.leave_channel(entity)
        return True, None
    except Exception as e:
        return False, str(e)

async def update_status(client, offline=False):
    """Update account status"""
    try:
        await client(functions.account.UpdateStatusRequest(offline=offline))
        return True
    except Exception:
        return False

async def set_privacy(client, privacy_type, value):
    """Set privacy settings"""
    try:
        await client(functions.account.SetPrivacyRequest(
            key=privacy_type,
            rules=[value]
        ))
        return True
    except Exception:
        return False

async def get_client_for_account(account):
    """Get Telegram client for an account"""
    session_string = account.get("session_string")
    if not session_string:
        return None
    
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        if await client.is_user_authorized():
            return client
        else:
            await client.disconnect()
            return None
    except Exception:
        return None

async def safe_disconnect(client):
    """Safely disconnect a client"""
    try:
        if client and client.is_connected():
            await client.disconnect()
    except Exception:
        pass

def parse_time_range(time_str):
    """Parse time range like min-1s max-8s"""
    try:
        min_time = None
        max_time = None
        
        # Extract min time
        min_match = re.search(r'min-(\d+)([sm]?)', time_str)
        if min_match:
            value = int(min_match.group(1))
            unit = min_match.group(2)
            min_time = value if unit == 's' else value * 60
        
        # Extract max time
        max_match = re.search(r'max-(\d+)([sm]?)', time_str)
        if max_match:
            value = int(max_match.group(1))
            unit = max_match.group(2)
            max_time = value if unit == 's' else value * 60
        
        return min_time, max_time
    except Exception:
        return None, None

async def random_delay(min_sec, max_sec):
    """Generate random delay between min and max seconds"""
    if min_sec and max_sec and min_sec < max_sec:
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
    elif min_sec:
        await asyncio.sleep(min_sec)

def validate_phone(phone):
    """Validate phone number format"""
    pattern = r'^\+?[1-9]\d{1,14}$'
    return re.match(pattern, phone) is not None

def format_account_info(account):
    """Format account information for display"""
    return f"ID: {account.get('id', 'Unknown')}\n" \
           f"Username: @{account.get('username', 'Unknown')}\n" \
           f"Status: {account.get('status', 'Unknown')}\n" \
           f"Mode: {account.get('mode', 'normal')}"
