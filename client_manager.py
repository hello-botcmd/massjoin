import asyncio
import logging
from telethon import TelegramClient, functions, types, errors
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    ApiIdInvalidError,
    PhoneNumberBannedError,
    RPCError,
)
from telethon.tl.types import PeerChannel
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

class ClientManager:
    def __init__(self):
        self.clients = {}            # phone -> TelegramClient
        self.online_tasks = {}       # phone -> asyncio.Task
        self._pending_logins = {}    # phone -> {client, phone_code_hash, awaiting_2fa}
        self._lock = asyncio.Lock()

    async def create_client(self, session_string: str, phone: str) -> TelegramClient:
        """Create and connect a Telethon client from a session string."""
        session = StringSession(session_string)
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            raise ValueError(f"Session for {phone} is not authorized")
        self.clients[phone] = client
        logger.info(f"Client for {phone} connected successfully")
        return client

    async def get_or_create_client(self, session_string: str, phone: str) -> TelegramClient:
        """Get existing client or create a new one."""
        if phone in self.clients:
            try:
                client = self.clients[phone]
                if client.is_connected():
                    return client
                await client.connect()
                if await client.is_user_authorized():
                    return client
            except Exception:
                pass
            try:
                del self.clients[phone]
            except KeyError:
                pass

        try:
            return await self.create_client(session_string, phone)
        except Exception as e:
            logger.error(f"Failed to create client for {phone}: {e}")
            return None

    async def get_client(self, phone: str) -> TelegramClient:
        """Get existing client by phone."""
        if phone in self.clients:
            client = self.clients[phone]
            if client.is_connected():
                return client
            try:
                await client.connect()
                if await client.is_user_authorized():
                    return client
            except Exception:
                pass
            del self.clients[phone]
            raise ConnectionError(f"Session for {phone} expired")
        raise KeyError(f"No client found for {phone}")

    async def disconnect_client(self, phone: str):
        """Disconnect and remove a client."""
        async with self._lock:
            await self.stop_online_ping(phone)
            if phone in self.clients:
                try:
                    await self.clients[phone].disconnect()
                except Exception:
                    pass
                del self.clients[phone]
                logger.info(f"Client for {phone} disconnected")

    async def disconnect_all(self):
        """Disconnect all clients."""
        phones = list(self.clients.keys())
        for phone in phones:
            await self.disconnect_client(phone)

    async def validate_session(self, session_string: str) -> tuple:
        """Validate a session string. Returns (success, phone, error)."""
        client = None
        try:
            session = StringSession(session_string)
            client = TelegramClient(session, API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, None, "Session is not authorized"
            me = await client.get_me()
            phone = me.phone or str(me.id)
            await client.disconnect()
            return True, phone, None
        except Exception as e:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            return False, None, str(e)[:200]

    async def start_phone_login(self, phone: str) -> tuple:
        """Send code request to phone."""
        phone = phone.strip()
        if not phone.startswith("+"):
            phone = "+" + phone

        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await client.disconnect()
            raise ValueError(f"Phone {phone} already has a session.")

        try:
            result = await client.send_code_request(phone, force_sms=False)
        except PhoneNumberInvalidError:
            await client.disconnect()
            raise ValueError("Invalid phone number. Use +1234567890 format")
        except PhoneNumberBannedError:
            await client.disconnect()
            raise ValueError("Phone number is banned from Telegram")
        except ApiIdInvalidError:
            await client.disconnect()
            raise ValueError("Invalid API_ID/API_HASH in config.py")
        except RPCError as e:
            await client.disconnect()
            raise ValueError(f"Telegram says: {str(e)[:200]}")
        except Exception as e:
            await client.disconnect()
            raise ValueError(str(e)[:200])

        self._pending_logins[phone] = {
            "client": client,
            "phone_code_hash": result.phone_code_hash,
        }
        return client, result.phone_code_hash

    async def submit_otp(self, phone: str, code: str) -> tuple:
        """Submit OTP. Returns (success, session_string or None, error)."""
        if not phone.startswith("+"):
            phone = "+" + phone

        pending = self._pending_logins.get(phone)
        if not pending:
            return False, None, "No pending login. Use /cancel and start again."

        client = pending["client"]
        phone_code_hash = pending["phone_code_hash"]

        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            session_string = client.session.save()
            self.clients[phone] = client
            self._pending_logins.pop(phone, None)
            return True, session_string, None
        except SessionPasswordNeededError:
            pending["awaiting_2fa"] = True
            return False, None, "2FA_REQUIRED"
        except PhoneCodeInvalidError:
            return False, None, "Invalid OTP code."
        except PhoneCodeExpiredError:
            await client.disconnect()
            self._pending_logins.pop(phone, None)
            return False, None, "OTP expired. Restart."
        except Exception as e:
            await client.disconnect()
            self._pending_logins.pop(phone, None)
            return False, None, str(e)[:200]

    async def submit_2fa(self, phone: str, password: str) -> tuple:
        """Submit 2FA password."""
        if not phone.startswith("+"):
            phone = "+" + phone

        pending = self._pending_logins.get(phone)
        if not pending or not pending.get("awaiting_2fa"):
            return False, None, "No pending 2FA. Restart login."

        client = pending["client"]
        try:
            await client.sign_in(password=password)
            session_string = client.session.save()
            self.clients[phone] = client
            self._pending_logins.pop(phone, None)
            return True, session_string, None
        except Exception as e:
            return False, None, f"Wrong 2FA: {str(e)[:200]}"

    async def cancel_pending_login(self, phone: str):
        """Cancel in-progress phone login."""
        if not phone.startswith("+"):
            phone = "+" + phone
        pending = self._pending_logins.pop(phone, None)
        if pending:
            try:
                await pending["client"].disconnect()
            except Exception:
                pass

    async def start_online_ping(self, phone: str):
        """Start background task to keep account online."""
        async with self._lock:
            if phone in self.online_tasks and not self.online_tasks[phone].done():
                return

            async def _ping_loop():
                from database import db
                try:
                    while True:
                        try:
                            client = await self.get_client(phone)
                            await client(functions.account.UpdateStatusRequest(offline=False))
                        except (KeyError, ConnectionError):
                            acc = await db.get_account(phone)
                            if acc and acc.get("session_string"):
                                try:
                                    client = await self.create_client(acc["session_string"], phone)
                                    await client(functions.account.UpdateStatusRequest(offline=False))
                                except Exception as e2:
                                    logger.error(f"Ping reconnect failed for {phone}: {e2}")
                        except Exception as e:
                            logger.error(f"Ping error for {phone}: {e}")
                        await asyncio.sleep(25)
                except asyncio.CancelledError:
                    logger.info(f"Online ping cancelled for {phone}")
                except Exception as e:
                    logger.error(f"Ping fatal for {phone}: {e}")

            task = asyncio.create_task(_ping_loop())
            self.online_tasks[phone] = task
            logger.info(f"Started online ping for {phone}")

    async def stop_online_ping(self, phone: str):
        """Stop online ping for a specific account."""
        async with self._lock:
            if phone in self.online_tasks:
                self.online_tasks[phone].cancel()
                del self.online_tasks[phone]

    async def stop_all_online_pings(self):
        """Stop all online ping tasks."""
        phones = list(self.online_tasks.keys())
        for phone in phones:
            await self.stop_online_ping(phone)

    async def set_offline(self, phone: str):
        """Set account offline explicitly."""
        try:
            client = await self.get_client(phone)
            await client(functions.account.UpdateStatusRequest(offline=True))
        except Exception as e:
            logger.warning(f"Could not set {phone} offline: {e}")

    async def set_online(self, phone: str):
        """Set account online one-time."""
        try:
            client = await self.get_client(phone)
            await client(functions.account.UpdateStatusRequest(offline=False))
        except Exception as e:
            logger.error(f"Failed to set {phone} online: {e}")

client_manager = ClientManager()
