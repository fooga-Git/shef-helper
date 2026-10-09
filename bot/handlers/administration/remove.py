from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User

router = Router(name="admin_remove")


@router.callback_query(F.data == "admin_remove")
async def show_list(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.role != "chef"))
        users = result.scalars().all()

    if not users:
        await callback.message.edit_text(
            "Нет сотрудников для удаления.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
            ]),
        )
        await callback.answer()
        return

    buttons = []
    for u in users:
        label = f"🗑 {u.full_name}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"remove_confirm_{u.telegram_id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выбери сотрудника для удаления:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("remove_confirm_"))
async def confirm_remove(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split("_", 2)[2])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"remove_do_{tg_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_remove"),
        ],
    ])
    ROLE_NAMES = {
        "chef": "Шеф-повар",
        "sous_chef": "Су-шеф",
        "cook": "Повар",
    }

    await callback.message.edit_text(
        f"Удалить сотрудника?\n\n"
        f"ФИО: {user.full_name}\n"
        f"Цех: {user.station or '—'}\n"
        f"Роль: {ROLE_NAMES.get(user.role, user.role)}",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_do_"))
async def do_remove(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split("_", 2)[2])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        name = user.full_name
        await session.delete(user)
        await session.commit()

    await callback.answer(f"{name} удалён.", show_alert=True)

    # возврат к списку
    await show_list(callback)
