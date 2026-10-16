import json
import calendar as cal_mod
from datetime import date, datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, distinct

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry, SalaryReport

router = Router(name="salary")

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


class SalaryFlow(StatesGroup):
    waiting_rate = State()
    waiting_accrual = State()
    waiting_accrual_date = State()
    waiting_penalty = State()
    waiting_penalty_date = State()
    waiting_advance_sum = State()
    waiting_salary_sum = State()
    waiting_undo_date = State()


def main_kb(user: User) -> InlineKeyboardMarkup:
    rate_text = f"{float(user.rate_amount):.0f} ₽/{'час' if user.rate_type == 'hour' else 'день'}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Начислить", callback_data="sal_accrual"),
         InlineKeyboardButton(text="➖ Отменить", callback_data="sal_undo")],
        [InlineKeyboardButton(text="⚠️ Штраф", callback_data="sal_penalty"),
         InlineKeyboardButton(text="💵 Получил", callback_data="sal_advance")],
        [InlineKeyboardButton(text="📊 Итог", callback_data="sal_total"),
         InlineKeyboardButton(text="📅 История", callback_data="sal_history")],
        [InlineKeyboardButton(text=f"⚙️ Ставка: {rate_text}", callback_data="sal_rate")],
    ])


def date_kb(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"{action}_today")],
        [InlineKeyboardButton(text="📆 Другая дата", callback_data=f"{action}_other")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")],
    ])


async def parse_date(text: str) -> date | None:
    text = text.strip()
    parts = text.replace("/", ".").replace("-", ".").split(".")
    try:
        if len(parts) == 2:
            day, month = int(parts[0]), int(parts[1])
            year = date.today().year
        elif len(parts) == 3:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            return None
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


async def is_month_closed(tg_id: int, year: int, month: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(SalaryReport).where(
                SalaryReport.telegram_id == tg_id,
                SalaryReport.year == year,
                SalaryReport.month == month,
            )
        )
        return result.scalar_one_or_none() is not None


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


# ---------- Начисление ----------

@router.callback_query(F.data == "sal_accrual")
async def ask_accrual(callback: CallbackQuery, state: FSMContext) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

    if not user:
        return

    if user.rate_type == "hour":
        await callback.message.edit_text("Введи количество часов:", reply_markup=date_kb("accrual"))
    else:
        await callback.message.edit_text("Введи коэффициент смены:", reply_markup=date_kb("accrual"))
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

    today = date.today()
    if d > today:
        await message.answer("❌ Нельзя начислить в будущем.")
        return

    if await is_month_closed(message.from_user.id, d.year, d.month):
        await message.answer(f"❌ {MONTHS_RU[d.month]} {d.year} уже закрыт.")
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

    unit = "ч" if user.rate_type == "hour" else "см"
    await state.clear()
    await message.answer(f"✅ Начислено за {target_date.strftime('%d.%m')}: {amount:.0f} ₽ ({value:g} {unit})")


# ---------- Отмена записи ----------

@router.callback_query(F.data == "sal_undo")
async def undo_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Выбери дату записи, которую отменить:",
        reply_markup=date_kb("undo"),
    )
    await callback.answer()


@router.callback_query(F.data == "undo_today")
async def undo_today(callback: CallbackQuery) -> None:
    d = date.today()
    await show_undo_list(callback, d)


@router.callback_query(F.data == "undo_other")
async def undo_other(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "📆 Введи дату в формате <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code>:"
    )
    await state.set_state(SalaryFlow.waiting_undo_date)
    await callback.answer()


@router.message(SalaryFlow.waiting_undo_date)
async def undo_date_input(message: Message, state: FSMContext) -> None:
    d = await parse_date(message.text)
    if not d:
        await message.answer("Неверный формат. Пример: <code>05.10</code>")
        return

    await state.clear()

    async with async_session() as session:
        result = await session.execute(
            select(SalaryEntry).where(
                SalaryEntry.telegram_id == message.from_user.id,
                SalaryEntry.entry_date == d,
            )
        )
        entries = result.scalars().all()

    if not entries:
        await message.answer(f"Нет записей за {d.strftime('%d.%m')}.")
        return

    buttons = []
    for e in entries:
        amount = float(e.amount)
        value = float(e.value)

        if e.entry_type == "accrual":
            label = f"➕ +{amount:.0f} ₽ ({value:g})"
        elif e.entry_type == "penalty":
            label = f"⚠️ {amount:.0f} ₽"
        elif e.entry_type == "advance":
            label = f"💵 {amount:.0f} ₽ (за {MONTHS_RU[e.month].lower()})"
        else:
            label = f"{amount:.0f} ₽"

        buttons.append([InlineKeyboardButton(text=label, callback_data=f"undo_entry_{e.id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(f"📅 {d.strftime('%d.%m.%Y')}\n\nВыбери запись для отмены:", reply_markup=kb)


async def show_undo_list(callback: CallbackQuery, d: date) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(SalaryEntry).where(
                SalaryEntry.telegram_id == callback.from_user.id,
                SalaryEntry.entry_date == d,
            )
        )
        entries = result.scalars().all()

    if not entries:
        await callback.answer(f"Нет записей за {d.strftime('%d.%m')}.", show_alert=True)
        return

    buttons = []
    for e in entries:
        amount = float(e.amount)
        value = float(e.value)

        if e.entry_type == "accrual":
            label = f"➕ +{amount:.0f} ₽ ({value:g})"
        elif e.entry_type == "penalty":
            label = f"⚠️ {amount:.0f} ₽"
        elif e.entry_type == "advance":
            label = f"💵 {amount:.0f} ₽ (за {MONTHS_RU[e.month].lower()})"
        else:
            label = f"{amount:.0f} ₽"

        buttons.append([InlineKeyboardButton(text=label, callback_data=f"undo_entry_{e.id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"📅 {d.strftime('%d.%m.%Y')}\n\nВыбери запись для отмены:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("undo_entry_"))
async def undo_confirm(callback: CallbackQuery) -> None:
    entry_id = int(callback.data.split("_", 2)[2])

    async with async_session() as session:
        result = await session.execute(select(SalaryEntry).where(SalaryEntry.id == entry_id))
        entry = result.scalar_one_or_none()

    if not entry:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    amount = float(entry.amount)
    d = entry.entry_date

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"undo_do_{entry_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="sal_back")],
    ])
    await callback.message.edit_text(
        f"Удалить запись?\n\n📅 {d.strftime('%d.%m.%Y')}\n💰 {amount:.0f} ₽",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("undo_do_"))
async def undo_do(callback: CallbackQuery) -> None:
    entry_id = int(callback.data.split("_", 2)[2])

    async with async_session() as session:
        result = await session.execute(select(SalaryEntry).where(SalaryEntry.id == entry_id))
        entry = result.scalar_one_or_none()

        if not entry:
            await callback.answer("Запись не найдена.", show_alert=True)
            return

        d = entry.entry_date
        await session.delete(entry)
        await session.commit()

    await callback.answer("✅ Удалено.", show_alert=True)

    # возврат к списку за ту же дату
    await show_undo_list(callback, d)


# ---------- Штраф ----------

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

    today = date.today()
    if d > today:
        await message.answer("❌ Нельзя штрафовать в будущем.")
        return

    if await is_month_closed(message.from_user.id, d.year, d.month):
        await message.answer(f"❌ {MONTHS_RU[d.month]} {d.year} уже закрыт.")
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


# ---------- Получил: аванс / зп ----------

async def get_open_months(tg_id: int) -> list[tuple[int, int]]:
    async with async_session() as session:
        entries = await session.execute(
            select(distinct(SalaryEntry.year), SalaryEntry.month)
            .where(SalaryEntry.telegram_id == tg_id)
        )
        entry_months = set(entries.all())

        reports = await session.execute(
            select(SalaryReport.year, SalaryReport.month)
            .where(SalaryReport.telegram_id == tg_id)
        )
        closed_months = set(reports.all())

    return sorted(entry_months - closed_months)


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

    buttons = [
        [InlineKeyboardButton(
            text=f"{MONTHS_RU[m]} {y}",
            callback_data=f"adv_month_{y}_{m}",
        )]
        for y, m in months
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_advance")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
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
    now = datetime.now()

    async with async_session() as session:
        entry = SalaryEntry(
            telegram_id=message.from_user.id,
            entry_type="advance",
            value=amount,
            amount=-amount,
            year=year,
            month=month,
            entry_date=now.date(),
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

    buttons = [
        [InlineKeyboardButton(
            text=f"{MONTHS_RU[m]} {y}",
            callback_data=f"sal_month_{y}_{m}",
        )]
        for y, m in months
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_advance")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
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


# ---------- Итог ----------

@router.callback_query(F.data == "sal_total")
async def show_total(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_res.scalar_one_or_none()

        lines = ["📊 <b>Итог</b>"]

        entries_res = await session.execute(
            select(SalaryEntry)
            .where(SalaryEntry.telegram_id == callback.from_user.id)
            .order_by(SalaryEntry.year, SalaryEntry.month)
        )
        entries = entries_res.scalars().all()

        grouped: dict[tuple[int, int], list[SalaryEntry]] = {}
        for e in entries:
            grouped.setdefault((e.year, e.month), []).append(e)

        unit = "ч" if user and user.rate_type == "hour" else "смен"

        for (year, month), month_entries in sorted(grouped.items()):
            accrued = sum(float(e.amount) for e in month_entries if e.entry_type == "accrual")
            penalty = sum(float(e.amount) for e in month_entries if e.entry_type == "penalty")
            advance = sum(float(e.amount) for e in month_entries if e.entry_type == "advance")
            shifts = sum(float(e.value) for e in month_entries if e.entry_type == "accrual")
            remainder = accrued + penalty + advance

            lines.append(
                f"\n<b>{MONTHS_RU[month]} {year}</b> (текущий)\n"
                f"  Отработано: {shifts:g} {unit}\n"
                f"  Начислено: {accrued:.0f} ₽\n"
                f"  Штрафы: {abs(penalty):.0f} ₽\n"
                f"  Аванс: {abs(advance):.0f} ₽\n"
                f"  Остаток: {remainder:.0f} ₽"
            )

        reports_res = await session.execute(
            select(SalaryReport)
            .where(SalaryReport.telegram_id == callback.from_user.id)
            .order_by(SalaryReport.year, SalaryReport.month)
        )
        reports = reports_res.scalars().all()

        for r in reports:
            lines.append(f"\n<b>{MONTHS_RU[r.month]} {r.year}</b> (закрыт)")
            if r.details:
                data = json.loads(r.details)
                shifts = data.get("shifts", 0)
                accrued = data.get("accrued", 0)
                penalties = data.get("penalties", [])
                advance = data.get("advance", 0)
                remainder = data.get("remainder", 0)

                lines.append(f"Смен: {shifts:g}")
                for p in penalties:
                    lines.append(f"  • {p['date']} — {p['amount']:.0f} ₽")
                if advance:
                    lines.append(f"Аванс: {advance:.0f} ₽")
                lines.append(f"ЗП: {remainder:.0f} ₽")
                lines.append("─────────────")
                lines.append(f"Без штрафов: {accrued:.0f} ₽")
                lines.append(f"Фактически: {accrued - abs(float(r.total_penalty)):.0f} ₽")

    if len(lines) == 1:
        await callback.answer("Пока пусто.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")],
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()


# ---------- История ----------

@router.callback_query(F.data == "sal_history")
async def show_history(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_res.scalar_one_or_none()

        entries_res = await session.execute(
            select(SalaryEntry)
            .where(SalaryEntry.telegram_id == callback.from_user.id)
            .order_by(SalaryEntry.year, SalaryEntry.month, SalaryEntry.entry_date)
        )
        entries = entries_res.scalars().all()

    if not entries:
        await callback.answer("Пока пусто.", show_alert=True)
        return

    unit = "ч" if user and user.rate_type == "hour" else "см"

    by_day: dict[tuple[int, int, int], list[SalaryEntry]] = {}
    months_open: set[tuple[int, int]] = set()
    for e in entries:
        key = (e.year, e.month, e.entry_date.day)
        by_day.setdefault(key, []).append(e)
        months_open.add((e.year, e.month))

    lines = ["📅 <b>История</b>"]

    today = date.today()

    for year, month in sorted(months_open):
        lines.append(f"\n<b>{MONTHS_RU[month]} {year}</b>")

        days_in_month = cal_mod.monthrange(year, month)[1]
        last_day = today.day if (year == today.year and month == today.month) else days_in_month

        for day in range(1, last_day + 1):
            day_entries = by_day.get((year, month, day), [])

            if not day_entries:
                lines.append(f"⚪ {day:02d}.{month:02d} — выходной")
                continue

            has_accrual = any(e.entry_type == "accrual" for e in day_entries)
            has_penalty = any(e.entry_type == "penalty" for e in day_entries)
            has_advance = any(e.entry_type == "advance" for e in day_entries)

            if has_advance and has_penalty:
                emoji = "🟡🔴"
            elif has_penalty:
                emoji = "🔴"
            elif has_advance:
                emoji = "🟡"
            elif has_accrual:
                emoji = "🟢"
            else:
                emoji = "⚪"

            parts = []
            if has_accrual:
                accrued_sum = sum(float(e.amount) for e in day_entries if e.entry_type == "accrual")
                accrued_val = sum(float(e.value) for e in day_entries if e.entry_type == "accrual")
                parts.append(f"+{accrued_sum:.0f} ₽ ({accrued_val:g} {unit})")
            if has_penalty:
                pen_sum = sum(abs(float(e.amount)) for e in day_entries if e.entry_type == "penalty")
                parts.append(f"штраф {pen_sum:.0f} ₽")
            if has_advance:
                adv_sum = sum(abs(float(e.amount)) for e in day_entries if e.entry_type == "advance")
                parts.append(f"аванс {adv_sum:.0f} ₽")

            lines.append(f"{emoji} {day:02d}.{month:02d} — {', '.join(parts)}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")],
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()
