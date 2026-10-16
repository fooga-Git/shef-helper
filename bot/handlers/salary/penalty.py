from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import SalaryEntry
from bot.keyboards.salary import date_kb
from bot.services.salary import parse_date, validate_date
from bot.services.salary_states import SalaryFlow

router = Router(name="sal_penalty")


@router.callback_query(F.data == "sal_penalty")
async def ask_penalty(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("Введи сумму штрафа:", reply_markup=date_kb("penalty"))
    await callback.answer()


@router.callback_query(F.data == "penalty_today")
async def penalty_today(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(target_date=date.today().isoformat())
    await callback.message.edit_text("Введи сумму штрафа:")
    await state.set_state(SalaryFlow.waiting_penalty)
    await callback.answer()


@router.callback_query(F.data == "penalty_other")
async def penalty_other(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "📆 Введи дату в формате <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code>:"
    )
    await state.set_state(SalaryFlow.waiting_penalty_date)
    await callback.answer()


@router.message(SalaryFlow.waiting_penalty_date)
async def penalty_date_input(message: Message, state: FSMContext) -> None:
    d = await parse_date(message.text)
    if not d:
        await message.answer("Неверный формат. Пример: <code>05.10</code>")
        return

    err = await validate_date(message.from_user.id, d)
    if err:
        await message.answer(err)
        return

    await state.update_data(target_date=d.isoformat())
    await message.answer("Введи сумму штрафа:")
    await state.set_state(SalaryFlow.waiting_penalty)


@router.message(SalaryFlow.waiting_penalty)
async def save_penalty(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число.")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше 0.")
        return

    data = await state.get_data()
    target_date_str = data.get("target_date")
    target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()

    async with async_session() as session:
        entry = SalaryEntry(
            telegram_id=message.from_user.id,
            entry_type="penalty",
            value=amount,
            amount=-amount,
            year=target_date.year,
            month=target_date.month,
            entry_date=target_date,
        )
        session.add(entry)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Штраф за {target_date.strftime('%d.%m')}: -{amount:.0f} ₽")
