from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User
from bot.keyboards.salary import main_kb
from bot.services.salary_states import SalaryFlow

router = Router(name="sal_menu")


@router.message(F.text == "💰 ЗП")
async def salary_menu(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

    if not user:
        return

    await message.answer("💰 <b>Зарплата</b>", reply_markup=main_kb(user))


@router.callback_query(F.data == "sal_back")
async def sal_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

    if not user:
        return

    await callback.message.edit_text("💰 <b>Зарплата</b>", reply_markup=main_kb(user))
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять.")
        return

    await state.clear()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

    if user:
        await message.answer("❌ Отменено.", reply_markup=main_kb(user))
    else:
        await message.answer("❌ Отменено.")


# ---------- Ставка ----------

@router.callback_query(F.data == "sal_rate")
async def ask_rate(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "⚙️ Введи ставку и тип через пробел.\n"
        "Например: <code>3000 день</code> или <code>500 час</code>"
    )
    await state.set_state(SalaryFlow.waiting_rate)
    await callback.answer()


@router.message(SalaryFlow.waiting_rate)
async def save_rate(message: Message, state: FSMContext) -> None:
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Неверный формат. Пример: <code>3000 день</code>")
        return

    try:
        amount = float(parts[0])
    except ValueError:
        await message.answer("Ставка должна быть числом.")
        return

    rate_type = parts[1].lower()
    if rate_type not in ("день", "час"):
        await message.answer("Тип: <code>день</code> или <code>час</code>")
        return

    rate_type = "day" if rate_type == "день" else "hour"

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.rate_type = rate_type
            user.rate_amount = amount
            await session.commit()

    await state.clear()
    await message.answer(f"✅ Ставка: {amount:.0f} ₽/{'час' if rate_type == 'hour' else 'день'}")
