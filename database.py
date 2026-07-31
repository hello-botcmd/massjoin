from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URI, DB_NAME
import asyncio

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.accounts = None
        self.lock = asyncio.Lock()
    
    async def initialize(self):
        if self.client is None:
            try:
                self.client = AsyncIOMotorClient(MONGODB_URI)
                self.db = self.client[DB_NAME]
                self.accounts = self.db.accounts
                await self.create_indexes()
                print("✅ Database connected successfully!")
            except Exception as e:
                print(f"❌ Database connection error: {e}")
                raise
    
    async def create_indexes(self):
        try:
            await self.accounts.create_index("_id", unique=True)  # _id is phone
            await self.accounts.create_index("session_string", unique=True)
            await self.accounts.create_index("username")
            await self.accounts.create_index("status")
            await self.accounts.create_index("mode")
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
    
    async def add_account(self, phone: str, session_string: str, username: str = None, **kwargs):
        """Add a new account."""
        async with self.lock:
            # Check if account exists
            existing = await self.accounts.find_one({"_id": phone})
            if existing:
                return False
            
            account_data = {
                "_id": phone,
                "phone": phone,
                "session_string": session_string,
                "username": username or f"user_{phone}",
                "status": "active",
                "mode": "normal",
                "privacy": "normal",
                "is_hidden": False,
                "last_seen": None,
                "is_online": False,
                "added_at": asyncio.get_event_loop().time(),
                **kwargs
            }
            
            try:
                await self.accounts.insert_one(account_data)
                return True
            except Exception as e:
                print(f"Error adding account: {e}")
                return False
    
    async def get_account(self, phone: str):
        """Get account by phone."""
        return await self.accounts.find_one({"_id": phone})
    
    async def get_all_accounts(self, filter_query=None):
        """Get all accounts."""
        if filter_query is None:
            filter_query = {}
        cursor = self.accounts.find(filter_query)
        return await cursor.to_list(length=None)
    
    async def get_active_accounts(self):
        """Get active accounts."""
        cursor = self.accounts.find({"status": "active"})
        return await cursor.to_list(length=None)
    
    async def update_account(self, phone: str, update_data: dict):
        """Update account by phone."""
        result = await self.accounts.update_one({"_id": phone}, {"$set": update_data})
        return result.modified_count
    
    async def update_many_accounts(self, filter_query, update_data):
        """Update multiple accounts."""
        result = await self.accounts.update_many(filter_query, {"$set": update_data})
        return result.modified_count
    
    async def delete_account(self, phone: str):
        """Delete account by phone."""
        result = await self.accounts.delete_one({"_id": phone})
        return result.deleted_count
    
    async def delete_many_accounts(self, filter_query):
        """Delete multiple accounts."""
        result = await self.accounts.delete_many(filter_query)
        return result.deleted_count
    
    async def get_account_count(self, filter_query=None):
        """Get account count."""
        if filter_query is None:
            filter_query = {}
        return await self.accounts.count_documents(filter_query)
    
    async def reset_all_profiles(self):
        """Reset all profiles to normal state."""
        await self.update_many_accounts(
            {},
            {
                "mode": "normal",
                "last_seen": None,
                "status": "active",
                "privacy": "normal",
                "is_hidden": False,
                "is_online": False
            }
        )

db = Database()
