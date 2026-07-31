import re
import asyncio
import logging
import random
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

# Stop events for users
_stop_events = {}
_online_tasks = {}

def get_stop_event(user_id):
    if user_id not in _stop_events:
        _stop_events[user_id] = asyncio.Event()
    return _stop_events[user_id]

def clear_stop_event(user_id):
    if user_id in _stop_events:
        _stop_events[user_id].clear()

def set_stop_event(user_id):
    ev = _stop_events.get(user_id)
    if ev:
        ev.set()

async def cancel_user_operations(user_id):
    ev = _stop_events.get(user_id)
    if ev:
        ev.set()

def parse_timing(timing_str):
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
    Join a channel/group. Returns (success, message).
    If already participant, returns (True, "Already a participant").
    """
    try:
        target = target.strip()
        logger.info(f"join_target: {target}")

        # Handle invite links
        if 't.me/joinchat/' in target or 't.me/+' in target:
            if '+' in target:
                hash_part = target.split('+')[-1]
            else:
                hash_part = target.split('joinchat/')[-1]
            hash_part = hash_part.split('?')[0].split('/')[0]
            try:
                await client(functions.messages.ImportChatInviteRequest(hash=hash_part))
                logger.info(f"Joined via invite: {target}")
                return True, "Joined via invite"
            except errors.rpcerrorlist.InviteHashInvalidError:
                return False, "Invalid invite link"
            except errors.rpcerrorlist.InviteHashExpiredError:
                return False, "Invite link expired"
            except errors.rpcerrorlist.UserAlreadyParticipantError:
                return True, "Already a participant"
            except Exception as e:
                return False, f"Invite error: {str(e)[:50]}"

        # Normalize username/link
        if 'https://t.me/' in target:
            target = target.split('https://t.me/')[-1]
        elif 't.me/' in target:
            target = target.split('t.me/')[-1]
        if target.startswith('@'):
            target = target[1:]
        target = target.split('/')[0]

        # Get entity
        try:
            entity = await client.get_entity(target)
        except ValueError:
            if target.lstrip('-').isdigit():
                entity = await client.get_entity(int(target))
            else:
                raise

        # Join
        await client(functions.channels.JoinChannelRequest(entity))
        logger.info(f"Joined: {target}")
        return True, "Joined successfully"

    except errors.rpcerrorlist.UserAlreadyParticipantError:
        return True, "Already a participant"
    except errors.rpcerrorlist.ChannelInvalidError:
        return False, "Invalid channel/group"
    except errors.rpcerrorlist.ChannelPrivateError:
        return False, "Channel is private or doesn't exist"
    except errors.rpcerrorlist.FloodWaitError as e:
        return False, f"Rate limited ({e.seconds}s)"
    except Exception as e:
        logger.error(f"Join error: {e}")
        return False, f"Error: {str(e)[:100]}"

async def get_fresh_client(session_string, timeout=10):
    """Create a fresh client, connect, and return if authorized."""
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=timeout)
        if await client.is_user_authorized():
            return client
        else:
            await client.disconnect()
            return None
    except Exception as e:
        logger.warning(f"Fresh client error: {e}")
        return None

async def safe_disconnect(client):
    try:
        if client and client.is_connected():
            await client.disconnect()
    except Exception:
        pass

async def update_status(client, offline=False):
    try:
        await client(functions.account.UpdateStatusRequest(offline=offline))
        return True
    except Exception:
        return False

async def set_privacy(client, privacy_key, rules):
    try:
        await client(functions.account.SetPrivacyRequest(key=privacy_key, rules=rules))
        return True
    except Exception:
        return False

async def reset_profile(client):
    """Reset privacy to default (allow contacts) and set online."""
    try:
        # Reset last seen privacy to default (allow contacts)
        await client(functions.account.SetPrivacyRequest(
            key=types.InputPrivacyKeyStatusTimestamp(),
            rules=[types.InputPrivacyValueAllowContacts()]
        ))
        # Set online
        await client(functions.account.UpdateStatusRequest(offline=False))
        return True
    except Exception as e:
        logger.error(f"Reset profile error: {e}")
        return False

def parse_mode_counts(text):
    """Parse '5,3,2' into tuple (5,3,2). Returns None if invalid."""
    parts = [p.strip() for p in text.split(',')]
    if len(parts) != 3:
        return None
    try:
        return tuple(int(p) for p in parts if p.isdigit())
    except:
        return None

def distribute_accounts(accounts, counts):
    """Distribute accounts into modes based on counts."""
    c1, c2, c3 = counts
    shuffled = list(accounts)
    random.shuffle(shuffled)
    assignments = []
    idx = 0
    for mode, cnt in enumerate([c1, c2, c3], start=1):
        for _ in range(cnt):
            if idx < len(shuffled):
                assignments.append((shuffled[idx], mode))
                idx += 1
    return assignments
