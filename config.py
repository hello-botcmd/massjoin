import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "telegram_bot")

# API Configuration
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# Session Configuration
SESSION_FILE = "sessions/"

# Timeouts
LOGIN_TIMEOUT = 30
JOIN_TIMEOUT = 60
REACTION_TIMEOUT = 30

# Allowed users (only owner and admins can use the bot)
ALLOWED_USERS = [OWNER_ID] + ADMIN_IDS
