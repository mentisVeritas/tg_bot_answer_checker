import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from db import create_tables
from handlers import common, user, admin


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )


    dp = Dispatcher(storage=MemoryStorage())

    # Создание таблиц при запуске
    create_tables()

    # Подключение всех хендлеров
    dp.include_routers(
        common.router,
        user.router,
        admin.router
    )

    print("🤖 Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())