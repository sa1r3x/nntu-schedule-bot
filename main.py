import asyncio
import logging
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher

load_dotenv()

import db_manager as db
from handlers import setup_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nntu_bot")


async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    if not os.getenv("LKS_TOKEN"):
        logger.error("LKS_TOKEN не задан в .env — расписание из ЛК работать не будет")

    db.init_db()
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(setup_routers())

    logger.info("ПолитехБот 26-ИВТ-2-1 запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
