import json
from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry, SalaryReport
from bot.keyboards.salary import month_picker_kb
from bot.services.salary import get_open_months, MONTHS_RU, unit_for
from bot.services.salary_states import SalaryFlow

router = Router(name="sal_advance")


@router.callback_query(F.data == "sal_advance")
async def show_advance_menu(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аванс", callback_data="sal_advance_part")],
        [InlineKeyboardButton(text="ЗП (закрыть месяц)", callback_data="sal_advance_full")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")],
    ])
    await callback.message.edit_text("💵 Что получил?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "sal_advance_part")
async def pick_month_for_advance(callback: CallbackQuery) -> None:
    months = await get_open_months(callback.from_user.id)
    if not months:
        await callback.answer("Нет открытых месяцев.", show_alert=True)
        return

    kb = month_picker_kb(months, "adv_month")
    await callback.message.edit_text("За какой месяц аванс?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("adv_month_"))
async def ask_advance_sum(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split("_")
    year, month = int(parts[2]), int(parts[3])
    await state.update_data(target_year=year, target_month=month)
    await callback.message.edit_text(f"Введи сумму аванса за {MONTHS_RU[month]} {year}:")
    await state.set_state(SalaryFlow.waiting_advance_sum)
    await callback.answer()


@router.message(SalaryFlow.waiting_advance_sum)
async def save_advance(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число.")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше 0.")
        return

    data = await state.get_data()
    year, month = data["target_year"], data["target_month"]

    async with async_session() as session:
        entry = SalaryEntry(
            telegram_id=message.from_user.id,
            entry_type="advance",
            value=amount,
            amount=-amount,
            year=year,
            month=month,
            entry_date=date.today(),
        )
        session.add(entry)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Аванс за {MONTHS_RU[month]} {year}: -{amount:.0f} ₽")


@router.callback_query(F.data == "sal_advance_full")
async def pick_month_for_salary(callback: CallbackQuery) -> None:
    months = await get_open_months(callback.from_user.id)
    if not months:
        await callback.answer("Нет открытых месяцев.", show_alert=True)
        return

    kb = month_picker_kb(months, "sal_month")
    await callback.message.edit_text("За какой месяц закрываем ЗП?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sal_month_"))
async def ask_salary_sum(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split("_")
    year, month = int(parts[2]), int(parts[3])
    await state.update_data(target_year=year, target_month=month)
    await callback.message.edit_text(f"Введи сумму полученной ЗП за {MONTHS_RU[month]} {year}:")
    await state.set_state(SalaryFlow.waiting_salary_sum)
    await callback.answer()


@router.message(SalaryFlow.waiting_salary_sum)
async def save_salary(message: Message, state: FSMContext) -> None:
    try:
        received = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число.")
        return

    if received < 0:
        await message.answer("Сумма не может быть отрицательной.")
        return

    data = await state.get_data()
    year, month = data["target_year"], data["target_month"]

    async with async_session() as session:
        result = await session.execute(
            select(SalaryEntry).where(
                SalaryEntry.telegram_id == message.from_user.id,
                SalaryEntry.year == year,
                SalaryEntry.month == month,
            )
        )
        entries = result.scalars().all()

        total_accrued = sum(float(e.amount) for e in entries if e.entry_type == "accrual")
        total_penalty = sum(float(e.amount) for e in entries if e.entry_type == "penalty")
        total_advance = sum(float(e.amount) for e in entries if e.entry_type == "advance")
        total_shifts = sum(float(e.value) for e in entries if e.entry_type == "accrual")

        penalties_details = [
            {"date": e.entry_date.strftime("%d.%m"), "amount": abs(float(e.amount))}
            for e in entries if e.entry_type == "penalty"
        ]

        details = {
            "shifts": total_shifts,
            "accrued": total_accrued,
            "penalties": penalties_details,
            "advance": abs(total_advance),
            "remainder": received,
        }

        report = SalaryReport(
            telegram_id=message.from_user.id,
            year=year,
            month=month,
            total_shifts=total_shifts,
            total_penalty=abs(total_penalty),
            total_advance=abs(total_advance),
            total_accrued=total_accrued,
            remainder=received,
            details=json.dumps(details, ensure_ascii=False),
        )
        session.add(report)

        for e in entries:
            await session.delete(e)

        await session.commit()

        user_res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_res.scalar_one_or_none()

    unit = "ч" if user and user.rate_type == "hour" else "смен"
    text = (
        f"📄 <b>Отчёт за {MONTHS_RU[month]} {year}</b>\n\n"
        f"Отработано: {total_shifts:g} {unit}\n"
        f"Начислено: {total_accrued:.0f} ₽\n"
        f"Штрафы: {abs(total_penalty):.0f} ₽\n"
        f"Аванс: {abs(total_advance):.0f} ₽\n"
        f"ЗП: {received:.0f} ₽"
    )

    await state.clear()
    await message.answer(text)
