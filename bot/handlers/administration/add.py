import secrets
import string

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
from aiogram.utils.deep_linking import create_start_link
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, Invite

router = Router(name="admin_add")


class AddEmployee(StatesGroup):
    full_name = State()
    station = State()


def generate_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def is_chef(telegram_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
    return user is not None and user.role == "chef"


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    if not await is_chef(message.from_user.id):
        await message.answer("Только шеф может добавлять сотрудников.")
        return

    await message.answer("Введи ФИО нового сотрудника:")
    await state.set_state(AddEmployee.full_name)


@router.callback_query(F.data == "admin_add")
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_chef(callback.from_user.id):
        await callback.answer("Доступ только для шефа.", show_alert=True)
        return

    await callback.message.answer("Введи ФИО нового сотрудника:")
    await state.set_state(AddEmployee.full_name)
    await callback.answer()


@router.message(AddEmployee.full_name)
async def process_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text.strip())
    await message.answer("Введи станцию (горячий цех, холодный, суши и т.д.):")
    await state.set_state(AddEmployee.station)


@router.message(AddEmployee.station)
async def process_station(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    full_name = data["full_name"]
    station = message.text.strip()

    code = generate_code()

    async with async_session() as session:
        invite = Invite(
            code=code,
            full_name=full_name,
            station=station,
            role="cook",
            created_by=message.from_user.id,
        )
        session.add(invite)
        await session.commit()

    link = await create_start_link(message.bot, code)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скопировать ссылку", copy_text=CopyTextButton(text=link))],
    ])

    await message.answer(
        f"✅ Приглашение создано!\n\n"
        f"ФИО: {full_name}\n"
        f"Станция: {station}\n"
        f"Код: <code>{code}</code>\n\n"
        f"Ссылка для сотрудника:\n{link}\n\n"
        f"Передай её сотруднику — он жмёт и регистрируется.",
        reply_markup=kb,
    )
    await state.clear()
