from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry
from bot.keyboards.salary import date_kb, back_kb
from bot.services.salary import parse_date, validate_date, unit_for
from bot.services.salary_states import SalaryFlow

router = Router(name="sal_accrual")


@router.callback_query(F.data == "sal_accrual")
async def ask_accrual(callback: CallbackQuery, state: FSMContext) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

    if not user:
        return

    if user.rate_type == "hour":
        text = "Введи количество часов:"
    else:
        text = "Введи коэффициент смены:"

    await callback.message.edit_text(text, reply_markup=date_kb("accrual"))
    await state.set_state(SalaryFlow.waiting_accrual)
    await callback.answer()


@router.callback_query(F.data == "accrual_today")
async def accrual_today(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(target_date=date.today().isoformat())
    await callback.message.edit_text("Введи значение:")
    await state.set_state(SalaryFlow.waiting_accrual)
    await callback.answer()


@router.callback_query(F.data == "accrual_other")
async def accrual_other(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "📆 Введи дату в формате <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code>:"
    )
    await state.set_state(SalaryFlow.waiting_accrual_date)
    await callback.answer()


@router.message(SalaryFlow.waiting_accrual_date)
async def accrual_date_input(message: Message, state: FSMContext) -> None:
    d = await parse_date(message.text)
    if not d:
        await message.answer("Неверный формат. Пример: <code>05.10</code>")
        return

    err = await validate_date(message.from_user.id, d)
    if err:
        await message.answer(err)
        return

    await state.update_data(target_date=d.isoformat())
    await message.answer("Введи значение:")
    await state.set_state(SalaryFlow.waiting_accrual)


@router.message(SalaryFlow.waiting_accrual)
async def save_accrual(message: Message, state: FSMContext) -> None:
    try:
        value = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число.")
        return

    if value <= 0:
        await message.answer("Число должно быть больше 0.")
        return

    data = await state.get_data()
    target_date_str = data.get("target_date")
    target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user:
            await state.clear()
            return

        existing = await session.execute(
            select(SalaryEntry).where(
                SalaryEntry.telegram_id == user.telegram_id,
                SalaryEntry.entry_type == "accrual",
                SalaryEntry.entry_date == target_date,
            )
        )
        if existing.scalar_one_or_none():
            await state.clear()
            await message.answer(f"❌ За {target_date.strftime('%d.%m')} уже начислено.")
            return

        amount = float(user.rate_amount) * value

        entry = SalaryEntry(
            telegram_id=user.telegram_id,
            entry_type="accrual",
            value=value,
            amount=amount,
            year=target_date.year,
            month=target_date.month,
            entry_date=target_date,
        )
        session.add(entry)
        await session.commit()

    unit = unit_for(user)
    await state.clear()
    await message.answer(f"✅ Начислено за {target_date.strftime('%d.%m')}: {amount:.0f} ₽ ({value:g} {unit})")
