import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))  # 👈 добавлено

if not BOT_TOKEN:
    raise ValueError("❌ Переменная окружения BOT_TOKEN не найдена в .env")

if not OWNER_ID:
    raise ValueError("❌ Переменная окружения OWNER_ID не найдена в .env")