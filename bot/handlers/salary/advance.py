import json
from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry, SalaryReport
from bot.keyboards.salary import month_picker_kb, date_kb
from bot.services.salary import get_open_months, MONTHS_RU, handle_date_input
from bot.services.salary_states import SalaryFlow

router = Router(name="sal_advance")


@router.callback_query(F.data == "sal_advance")
async def show_advance_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аванс", callback_data="sal_advance_part")],
        [InlineKeyboardButton(text="ЗП (закрыть месяц)", callback_data="sal_advance_full")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")],
    ])
    await callback.message.edit_text("💵 Что получил?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "sal_advance_part")
async def pick_month_for_advance(callback: CallbackQuery, state: FSMContext) -> None:
    months = await get_open_months(callback.from_user.id)
    if not months:
        await callback.answer("Нет открытых месяцев.", show_alert=True)
        return

    await state.update_data(kind="advance")
    kb = month_picker_kb(months, "adv_month")
    await callback.message.edit_text("За какой месяц аванс?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("adv_month_"))
async def ask_advance_date(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split("_")
    year, month = int(parts[2]), int(parts[3])
    await state.update_data(target_year=year, target_month=month, kind="advance")

    await callback.message.edit_text(
        f"Дата выдачи аванса за {MONTHS_RU[month]} {year}:",
        reply_markup=date_kb("adv_date"),
    )
    await callback.answer()


@router.callback_query(F.data == "sal_advance_full")
async def pick_month_for_salary(callback: CallbackQuery, state: FSMContext) -> None:
    months = await get_open_months(callback.from_user.id)
    if not months:
        await callback.answer("Нет открытых месяцев.", show_alert=True)
        return

    await state.update_data(kind="salary")
    kb = month_picker_kb(months, "sal_month")
    await callback.message.edit_text("За какой месяц закрываем ЗП?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sal_month_"))
async def ask_salary_date(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split("_")
    year, month = int(parts[2]), int(parts[3])
    await state.update_data(target_year=year, target_month=month, kind="salary")

    await callback.message.edit_text(
        f"Дата выдачи ЗП за {MONTHS_RU[month]} {year}:",
        reply_markup=date_kb("sal_date"),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^(adv_date|sal_date)_today$"))
async def date_today(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(paid_date=date.today().isoformat())
    await callback.message.edit_text("Введи сумму:")
    await state.set_state(SalaryFlow.advance_value)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^(adv_date|sal_date)_other$"))
async def date_other(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "📆 Введи дату в формате <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code>:"
    )
    await state.set_state(SalaryFlow.advance_date)
    await callback.answer()


@router.message(SalaryFlow.advance_date)
async def date_input(message: Message, state: FSMContext) -> None:
    d, err = await handle_date_input(message.text, message.from_user.id)
    if err:
        await message.answer(err)
        return

    await state.update_data(paid_date=d.isoformat())
    await message.answer("Введи сумму:")
    await state.set_state(SalaryFlow.advance_value)


@router.message(SalaryFlow.advance_value)
async def save_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    kind = data.get("kind")

    if kind not in ("advance", "salary"):
        await state.clear()
        return

    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число.")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше 0.")
        return

    year = data["target_year"]
    month = data["target_month"]
    paid_date_str = data.get("paid_date")
    paid_date = date.fromisoformat(paid_date_str) if paid_date_str else date.today()

    if kind == "advance":
        await _save_advance(message, state, year, month, paid_date, amount)
    else:
        await _save_salary(message, state, year, month, paid_date, amount)


async def _save_advance(message: Message, state: FSMContext, year: int, month: int, paid_date: date, amount: float) -> None:
    async with async_session() as session:
        entry = SalaryEntry(
            telegram_id=message.from_user.id,
            entry_type="advance",
            value=amount,
            amount=-amount,
            year=year,
            month=month,
            entry_date=paid_date,
        )
        session.add(entry)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Аванс за {MONTHS_RU[month]} {year}: -{amount:.0f} ₽\n📅 Выдан: {paid_date.strftime('%d.%m')}")


async def _save_salary(message: Message, state: FSMContext, year: int, month: int, paid_date: date, received: float) -> None:
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
            "paid_date": paid_date.strftime("%d.%m.%Y"),
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
        f"ЗП: {received:.0f} ₽\n"
        f"📅 Выдано: {paid_date.strftime('%d.%m.%Y')}"
    )

    await state.clear()
    await message.answer(text)
