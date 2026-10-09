from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # пропускаем /start — чтобы новый мог зарегаться
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if not user_id:
            return await handler(event, data)

        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()

        if not user:
            # игнорируем — не отвечаем
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён.", show_alert=True)
            return

        # кладём юзера в data, чтобы хендлеры могли использовать
        data["user"] = user
        return await handler(event, data)
