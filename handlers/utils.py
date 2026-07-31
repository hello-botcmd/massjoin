from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SESSION_FILE
import asyncio
import random
import time
import os

async def login_account(session_string, phone=None):
    """Login to Telegram using session string"""
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
        return False, None

async def join_channel(client, channel_username):
    """Join a channel/group"""
    try:
        entity = await client.get_entity(channel_username)
        await client.join_channel(entity)
        return True, None
    except errors.rpcerrorlist.ChannelInvalidError:
        return False, "Invalid channel"
    except errors.rpcerrorlist.ChannelPrivateError:
        return False, "Channel is private"
    except errors.rpcerrorlist.UserAlreadyParticipantError:
        return False, "Already a participant"
    except Exception as e:
        return False, str(e)

async def leave_channel(client, channel_username):
    """Leave a channel/group"""
    try:
        entity = await client.get_entity(channel_username)
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
        parts = time_str.split()
        min_time = None
        max_time = None
        
        for part in parts:
            if part.startswith('min-'):
                value = part[4:].replace('s', '').replace('m', '')
                min_time = int(value)
                if 'm' in part[4:]:
                    min_time *= 60
            elif part.startswith('max-'):
                value = part[4:].replace('s', '').replace('m', '')
                max_time = int(value)
                if 'm' in part[4:]:
                    max_time *= 60
        
        return min_time, max_time
    except Exception:
        return None, None

async def random_delay(min_sec, max_sec):
    """Generate random delay between min and max seconds"""
    if min_sec and max_sec:
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

def validate_phone(phone):
    """Validate phone number format"""
    import re
    pattern = r'^\+?[1-9]\d{1,14}$'
    return re.match(pattern, phone) is not None

def format_account_info(account):
    """Format account information for display"""
    return f"ID: {account.get('id', 'Unknown')}\n" \
           f"Username: @{account.get('username', 'Unknown')}\n" \
           f"Status: {account.get('status', 'Unknown')}\n" \
           f"Mode: {account.get('mode', 'normal')}"
