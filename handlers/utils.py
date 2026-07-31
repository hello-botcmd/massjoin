import re
import asyncio
import random
import logging
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

# Stop events for users
_stop_events = {}

def get_stop_event(user_id):
    """Get or create a stop event for a user"""
    if user_id not in _stop_events:
        _stop_events[user_id] = asyncio.Event()
    return _stop_events[user_id]

def clear_stop_event(user_id):
    """Clear the stop event for a user"""
    if user_id in _stop_events:
        _stop_events[user_id].clear()

def parse_timing(timing_str):
    """Parse timing string like 'min-1s max-8s' or '2 6'"""
    try:
        min_time = None
        max_time = None
        
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

async def join_target(client, target):
    """
    Join a channel/group - handles public, private, invite links, and channels by ID.
    Returns (success, message)
    """
    try:
        target = target.strip()
        logger.info(f"Attempting to join: {target}")
        
        # Handle invite links (private groups/channels)
        if 't.me/joinchat/' in target or 't.me/+' in target or 't.me/joinchat' in target:
            # Extract hash
            if '+' in target:
                hash_part = target.split('+')[-1]
            else:
                hash_part = target.split('joinchat/')[-1]
            # Remove any trailing slashes or query params
            hash_part = hash_part.split('?')[0].split('/')[0]
            try:
                await client(functions.messages.ImportChatInviteRequest(hash=hash_part))
                logger.info(f"Joined via invite link: {target}")
                return True, "Joined via invite link"
            except errors.rpcerrorlist.InviteHashInvalidError:
                return False, "Invalid invite link"
            except errors.rpcerrorlist.InviteHashExpiredError:
                return False, "Invite link expired"
            except Exception as e:
                return False, f"Invite error: {str(e)[:50]}"
        
        # Clean up normal username/channel links
        if 'https://t.me/' in target:
            target = target.split('https://t.me/')[-1]
        elif 't.me/' in target:
            target = target.split('t.me/')[-1]
        
        if target.startswith('@'):
            target = target[1:]
        
        # Remove any trailing slashes
        target = target.split('/')[0]
        
        # Get entity
        try:
            entity = await client.get_entity(target)
        except ValueError as e:
            # Maybe it's a numeric ID
            if target.lstrip('-').isdigit():
                entity = await client.get_entity(int(target))
            else:
                raise e
        
        # Join the channel/group
        try:
            await client(functions.channels.JoinChannelRequest(entity))
            logger.info(f"Joined successfully: {target}")
            return True, "Joined successfully"
        except errors.rpcerrorlist.UserAlreadyParticipantError:
            logger.info(f"Already a participant: {target}")
            return True, "Already a participant"
            
    except errors.rpcerrorlist.ChannelInvalidError:
        return False, "Invalid channel or group"
    except errors.rpcerrorlist.ChannelPrivateError:
        return False, "Channel is private or doesn't exist"
    except errors.rpcerrorlist.FloodWaitError as e:
        return False, f"Rate limited. Wait {e.seconds}s"
    except Exception as e:
        logger.error(f"Join error: {e}")
        return False, f"Error: {str(e)[:100]}"

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
