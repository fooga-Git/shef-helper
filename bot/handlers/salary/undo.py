from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry
from bot.keyboards.salary import date_kb
from bot.services.salary import parse_date, entry_label
from bot.services.salary_states import SalaryFlow

router = Router(name="sal_undo")


def _list_kb(entries: list[SalaryEntry], user: User | None) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=entry_label(e, user),
            callback_data=f"undo_entry_{e.id}",
        )]
        for e in entries
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sal_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _show_for_date(callback: CallbackQuery, d: date) -> None:
    async with async_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_res.scalar_one_or_none()

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

    await callback.message.edit_text(
        f"📅 {d.strftime('%d.%m.%Y')}\n\nВыбери запись для отмены:",
        reply_markup=_list_kb(entries, user),
    )
    await callback.answer()


@router.callback_query(F.data == "sal_undo")
async def undo_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Выбери дату записи, которую отменить:",
        reply_markup=date_kb("undo"),
    )
    await callback.answer()


@router.callback_query(F.data == "undo_today")
async def undo_today(callback: CallbackQuery) -> None:
    await _show_for_date(callback, date.today())


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
        user_res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_res.scalar_one_or_none()

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

    await message.answer(
        f"📅 {d.strftime('%d.%m.%Y')}\n\nВыбери запись для отмены:",
        reply_markup=_list_kb(entries, user),
    )


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
    await _show_for_date(callback, d)
