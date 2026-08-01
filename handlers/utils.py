import re
import asyncio
import logging
import random
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

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
    try:
        target = target.strip()
        if 't.me/joinchat/' in target or 't.me/+' in target:
            if '+' in target:
                hash_part = target.split('+')[-1]
            else:
                hash_part = target.split('joinchat/')[-1]
            hash_part = hash_part.split('?')[0].split('/')[0]
            try:
                await client(functions.messages.ImportChatInviteRequest(hash=hash_part))
                return True, "Joined via invite"
            except errors.rpcerrorlist.InviteHashInvalidError:
                return False, "Invalid invite link"
            except errors.rpcerrorlist.InviteHashExpiredError:
                return False, "Invite link expired"
            except errors.rpcerrorlist.UserAlreadyParticipantError:
                return True, "Already a participant"
            except Exception as e:
                return False, f"Invite error: {str(e)[:50]}"
        if 'https://t.me/' in target:
            target = target.split('https://t.me/')[-1]
        elif 't.me/' in target:
            target = target.split('t.me/')[-1]
        if target.startswith('@'):
            target = target[1:]
        target = target.split('/')[0]
        try:
            entity = await client.get_entity(target)
        except ValueError:
            if target.lstrip('-').isdigit():
                entity = await client.get_entity(int(target))
            else:
                raise
        await client(functions.channels.JoinChannelRequest(entity))
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

# ---------- ROBUST PRIVACY SETTER (FIXES PROFILE UPDATION) ----------
async def set_last_seen_privacy(client, show_last_seen: bool) -> bool:
    """
    Show/hide last seen + online presence for everyone.
    Order matters:
      * HIDE (show=False): first StatusTimestamp, then Presence
      * SHOW (show=True):  first Presence, then StatusTimestamp
    With verification and retry.
    """
    rule = (types.InputPrivacyValueAllowAll() if show_last_seen
            else types.InputPrivacyValueDisallowAll())

    keys = ([types.InputPrivacyKeyStatusTimestamp(),
             types.InputPrivacyKeyPresence()]
            if not show_last_seen else
            [types.InputPrivacyKeyPresence(),
             types.InputPrivacyKeyStatusTimestamp()])

    for attempt in range(3):
        try:
            for key in keys:
                await client(functions.account.SetPrivacyRequest(key=key, rules=[rule]))
                await asyncio.sleep(0.4)  # server sync

            # Verify
            ok = True
            for key in keys:
                res = await client(functions.account.GetPrivacyRequest(key=key))
                allowed = any(isinstance(r, types.PrivacyValueAllowAll) for r in res.rules)
                if allowed != show_last_seen:
                    ok = False
                    break
            if ok:
                return True
            logger.warning(f"privacy verify mismatch (show={show_last_seen}), retry {attempt + 1}")
            await asyncio.sleep(1.0)
        except errors.rpcerrorlist.FloodWaitError as e:
            logger.warning(f"setPrivacy flood {e.seconds}s, waiting...")
            await asyncio.sleep(min(e.seconds + 1, 60))
        except Exception as e:
            logger.warning(f"setPrivacy error: {e}, retry {attempt + 1}")
            await asyncio.sleep(1.0)
    return False

async def set_online_status(client, offline: bool) -> bool:
    """Flood-aware status update."""
    try:
        await client(functions.account.UpdateStatusRequest(offline=offline))
        return True
    except errors.rpcerrorlist.FloodWaitError as e:
        logger.warning(f"updateStatus flood {e.seconds}s, waiting...")
        await asyncio.sleep(min(e.seconds + 1, 60))
        try:
            await client(functions.account.UpdateStatusRequest(offline=offline))
            return True
        except Exception:
            return False
    except Exception:
        return False

# ---------- PARSING HELPERS ----------
def parse_mode_counts(text):
    parts = [p.strip() for p in text.split(',')]
    if len(parts) != 3:
        return None
    try:
        counts = tuple(int(p) for p in parts)
    except (ValueError, TypeError):
        return None
    if any(c < 0 for c in counts):
        return None
    return counts

def distribute_accounts(accounts, counts):
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
