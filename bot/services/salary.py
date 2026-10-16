from datetime import date

from sqlalchemy import select, distinct

from bot.db.base import async_session
from bot.db.models import SalaryEntry, SalaryReport

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}

UNIT_BY_TYPE = {"hour": "ч", "day": "см"}


def unit_for(user) -> str:
    return UNIT_BY_TYPE.get(user.rate_type, "см")


def parse_date(text: str) -> date | None:
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


async def validate_date(tg_id: int, d: date) -> str | None:
    if d > date.today():
        return "❌ Нельзя в будущем."
    if await is_month_closed(tg_id, d.year, d.month):
        return f"❌ {MONTHS_RU[d.month]} {d.year} уже закрыт."
    return None


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


def entry_label(entry: SalaryEntry, user=None) -> str:
    amount = float(entry.amount)
    value = float(entry.value)

    if entry.entry_type == "accrual":
        unit = UNIT_BY_TYPE.get(user.rate_type, "см") if user else "см"
        return f"➕ +{amount:.0f} ₽ ({value:g} {unit})"
    if entry.entry_type == "penalty":
        return f"⚠️ {amount:.0f} ₽"
    if entry.entry_type == "advance":
        return f"💵 {amount:.0f} ₽ (за {MONTHS_RU[entry.month].lower()})"
    return f"{amount:.0f} ₽"


async def handle_date_input(text: str, tg_id: int) -> tuple[date | None, str | None]:
    """Парсит и валидирует дату. Возвращает (date, error)."""
    d = parse_date(text)
    if not d:
        return None, "Неверный формат. Пример: <code>05.10</code>"

    err = await validate_date(tg_id, d)
    if err:
        return None, err

    return d, None


async def handle_date_input(text: str, tg_id: int) -> tuple[date | None, str | None]:
    """Парсит и валидирует дату. Возвращает (date, error_message)."""
    d = parse_date(text)
    if not d:
        return None, "Неверный формат. Пример: <code>05.10</code>"

    err = await validate_date(tg_id, d)
    if err:
        return None, err

    return d, None
