import re
import asyncio
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH

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
        
        # Join using the correct method
        await client(functions.channels.JoinChannelRequest(entity))
        return True, "Success"
            
    except errors.rpcerrorlist.ChannelInvalidError:
        return False, "Invalid channel or group"
    except errors.rpcerrorlist.ChannelPrivateError:
        return False, "Channel is private or doesn't exist"
    except errors.rpcerrorlist.UserAlreadyParticipantError:
        return True, "Already a participant"
    except errors.rpcerrorlist.FloodWaitError as e:
        return False, f"Rate limited. Wait {e.seconds}s"
    except Exception as e:
        return False, str(e)[:100]
