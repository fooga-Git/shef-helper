import asyncio
import logging
import ssl

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from raito import Raito
from andro_cfw import CFWSession

from bot.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    cfw = CFWSession.load()
    api_server = TelegramAPIServer(**cfw.aiogram_server_url())

    session = AiohttpSession(api=api_server)

    # Засовываем SSL-контекст внутрь коннектора aiohttp
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    session._connector_init["ssl"] = ssl_ctx

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    raito = Raito(
        dp,
        "/home/house/shef-helper/shef-helper/bot/handlers",
        production=False,
    )
    await raito.setup()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
