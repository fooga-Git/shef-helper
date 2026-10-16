import json

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry, SalaryReport
from bot.keyboards.salary import back_kb
from bot.services.salary import MONTHS_RU, unit_for

router = Router(name="sal_total")


@router.callback_query(F.data == "sal_total")
async def show_total(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_res.scalar_one_or_none()

        lines = ["📊 <b>Итог</b>"]

        # Открытые месяцы
        entries_res = await session.execute(
            select(SalaryEntry)
            .where(SalaryEntry.telegram_id == callback.from_user.id)
            .order_by(SalaryEntry.year, SalaryEntry.month)
        )
        entries = entries_res.scalars().all()

        grouped: dict[tuple[int, int], list[SalaryEntry]] = {}
        for e in entries:
            grouped.setdefault((e.year, e.month), []).append(e)

        unit = unit_for(user) if user else "смен"

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

        # Закрытые
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

    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb())
    await callback.answer()
