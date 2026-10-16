from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.db.models import User
from bot.services.salary import MONTHS_RU


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


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")],
    ])


def month_picker_kb(months: list[tuple[int, int]], action_prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{MONTHS_RU[m]} {y}",
            callback_data=f"{action_prefix}_{y}_{m}",
        )]
        for y, m in months
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_advance")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
