import asyncio

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BotCommand
from sqlalchemy import select, func

from bot.db.base import async_session
from bot.db.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    tg_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()

        if user:
            await message.answer(f"С возвращением, {user.full_name}! Твоя роль: {user.role}")
            return

        count = await session.scalar(select(func.count()).select_from(User))
        role = "chef" if count == 0 else "cook"

        new_user = User(
            telegram_id=tg_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            role=role,
        )
        session.add(new_user)
        await session.commit()

        if role == "chef":
            await message.answer(f"Ты первый! Добро пожаловать, шеф {message.from_user.full_name}.")
        else:
            await message.answer(f"Привет, {message.from_user.full_name}! Ты зарегистрирован как повар.")


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    chat_id = message.chat.id
    bot = message.bot

    # удаляем сообщение с командой
    try:
        await message.delete()
    except Exception:
        pass

    # собираем список id, которые пробуем удалить (последние 200)
    ids = list(range(message.message_id, max(message.message_id - 200, 0), -1))

    # параллельно, но с ограничением в 25 запросов одновременно
    sem = asyncio.Semaphore(25)

    async def try_delete(msg_id: int) -> bool:
        async with sem:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                return True
            except Exception:
                return False

    results = await asyncio.gather(*(try_delete(i) for i in ids))
    deleted = sum(results)

    await bot.send_message(chat_id=chat_id, text=f"Очищено сообщений: {deleted}")
