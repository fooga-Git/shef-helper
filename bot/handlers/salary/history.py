import calendar as cal_mod
from datetime import date

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry
from bot.keyboards.salary import back_kb
from bot.services.salary import MONTHS_RU, unit_for

router = Router(name="sal_history")


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

    unit = unit_for(user) if user else "см"

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
                acc_sum = sum(float(e.amount) for e in day_entries if e.entry_type == "accrual")
                acc_val = sum(float(e.value) for e in day_entries if e.entry_type == "accrual")
                parts.append(f"+{acc_sum:.0f} ₽ ({acc_val:g} {unit})")
            if has_penalty:
                pen_sum = sum(abs(float(e.amount)) for e in day_entries if e.entry_type == "penalty")
                parts.append(f"штраф {pen_sum:.0f} ₽")
            if has_advance:
                adv_sum = sum(abs(float(e.amount)) for e in day_entries if e.entry_type == "advance")
                parts.append(f"аванс {adv_sum:.0f} ₽")

            lines.append(f"{emoji} {day:02d}.{month:02d} — {', '.join(parts)}")

    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb())
    await callback.answer()
