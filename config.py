import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required in .env file")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "telegram_bot")

# API Configuration
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

if API_ID == 0 or not API_HASH:
    raise ValueError("API_ID and API_HASH are required in .env file")

# Allowed users (only owner and admins can use the bot)
ALLOWED_USERS = [OWNER_ID] + ADMIN_IDS

print(f"✅ Config loaded successfully!")
print(f"👤 Owner ID: {OWNER_ID}")
print(f"👥 Admin IDs: {ADMIN_IDS}")
print(f"📊 Allowed users: {ALLOWED_USERS}")
