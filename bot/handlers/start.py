import asyncio

from aiogram import Router
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, BotCommand, BotCommandScopeChat
from sqlalchemy import select, func

from bot.db.base import async_session
from bot.db.models import User, Invite
from bot.keyboards.main_menu import main_menu

router = Router(name="start")


async def set_chef_commands(bot, chat_id: int) -> None:
    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="Начать"),
            BotCommand(command="clear", description="Очистить чат"),
        ],
        scope=BotCommandScopeChat(chat_id=chat_id),
    )


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, command: CommandObject) -> None:
    code = command.args
    if not code:
        await message.answer("Некорректная ссылка.")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        existing = result.scalar_one_or_none()
        if existing:
            await message.answer(f"Ты уже зарегистрирован как {existing.full_name}.")
            return

        result = await session.execute(
            select(Invite).where(Invite.code == code, Invite.is_used == False)  # noqa: E712
        )
        invite = result.scalar_one_or_none()

        if not invite:
            await message.answer("Приглашение не найдено или уже использовано.")
            return

        new_user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=invite.full_name,
            role=invite.role,
            station=invite.station,
        )
        session.add(new_user)
        invite.is_used = True
        await session.commit()

    await message.answer(
        f"✅ Добро пожаловать, {invite.full_name}!\n"
        f"Станция: {invite.station}\n"
        f"Роль: {invite.role}",
        reply_markup=main_menu(invite.role),
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    tg_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()

        if user:
            await message.answer(
                f"Привет, {user.full_name}!",
                reply_markup=main_menu(user.role),
            )
            return

        count = await session.scalar(select(func.count()).select_from(User))

        if count == 0:
            new_user = User(
                telegram_id=tg_id,
                username=message.from_user.username,
                full_name=message.from_user.full_name,
                role="chef",
            )
            session.add(new_user)
            await session.commit()
            await message.answer(
                f"Ты первый! Добро пожаловать, шеф {message.from_user.full_name}.",
                reply_markup=main_menu("chef"),
            )
            await set_chef_commands(message.bot, tg_id)
            return

    await message.answer("Привет! Доступ к боту — только по приглашению.")


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    chat_id = message.chat.id
    bot = message.bot

    try:
        await message.delete()
    except Exception:
        pass

    ids = list(range(message.message_id, max(message.message_id - 200, 0), -1))
    sem = asyncio.Semaphore(25)

    async def try_delete(msg_id: int) -> bool:
        async with sem:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                return True
            except Exception:
                return False

    await asyncio.gather(*(try_delete(i) for i in ids))
