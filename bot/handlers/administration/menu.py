from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User

router = Router(name="administration")


@router.message(F.text == "👔 Администрация команды")
async def btn_admin(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

    if not user or user.role != "chef":
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить сотрудника",
                              callback_data="admin_add")],
        [InlineKeyboardButton(text="➖ Удалить сотрудника",
                              callback_data="admin_remove")],
        [InlineKeyboardButton(text="📋 Список сотрудников",
                              callback_data="admin_list")],
    ])
    await message.answer("👔 <b>Администрация команды</b>\n\nВыбери действие:", reply_markup=kb)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

    if not user or user.role != "chef":
        await message.answer("Доступ только для шефа.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить сотрудника",
                              callback_data="admin_add")],
        [InlineKeyboardButton(text="➖ Удалить сотрудника",
                              callback_data="admin_remove")],
        [InlineKeyboardButton(text="📋 Список сотрудников",
                              callback_data="admin_list")],
    ])
    await message.answer("👔 <b>Администрация команды</b>\n\nВыбери действие:", reply_markup=kb)


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить сотрудника",
                              callback_data="admin_add")],
        [InlineKeyboardButton(text="➖ Удалить сотрудника",
                              callback_data="admin_remove")],
        [InlineKeyboardButton(text="📋 Список сотрудников",
                              callback_data="admin_list")],
    ])
    await callback.message.edit_text("👔 <b>Администрация команды</b>\n\nВыбери действие:", reply_markup=kb)
    await callback.answer()
