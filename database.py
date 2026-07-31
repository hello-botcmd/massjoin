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
            await self.accounts.create_index("session_string", unique=True)
            await self.accounts.create_index("username")
            await self.accounts.create_index("status")
            await self.accounts.create_index("mode")
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
    
    async def add_account(self, account_data):
        async with self.lock:
            result = await self.accounts.insert_one(account_data)
            return result.inserted_id
    
    async def add_bulk_accounts(self, accounts_data):
        async with self.lock:
            if accounts_data:
                result = await self.accounts.insert_many(accounts_data)
                return len(result.inserted_ids)
            return 0
    
    async def get_account(self, query):
        return await self.accounts.find_one(query)
    
    async def get_all_accounts(self, filter_query=None):
        if filter_query is None:
            filter_query = {}
        cursor = self.accounts.find(filter_query)
        return await cursor.to_list(length=None)
    
    async def get_active_accounts(self):
        cursor = self.accounts.find({"status": "active"})
        return await cursor.to_list(length=None)
    
    async def update_account(self, query, update_data):
        result = await self.accounts.update_one(query, {"$set": update_data})
        return result.modified_count
    
    async def update_many_accounts(self, filter_query, update_data):
        result = await self.accounts.update_many(filter_query, {"$set": update_data})
        return result.modified_count
    
    async def delete_account(self, query):
        result = await self.accounts.delete_one(query)
        return result.deleted_count
    
    async def delete_many_accounts(self, query):
        result = await self.accounts.delete_many(query)
        return result.deleted_count
    
    async def get_account_count(self, filter_query=None):
        if filter_query is None:
            filter_query = {}
        return await self.accounts.count_documents(filter_query)
    
    async def get_accounts_by_mode(self, mode):
        return await self.get_all_accounts({"mode": mode})
    
    async def reset_all_profiles(self):
        await self.update_many_accounts(
            {},
            {
                "mode": "normal",
                "last_seen": None,
                "status": "active",
                "privacy": "normal",
                "is_hidden": False
            }
        )

db = Database()
