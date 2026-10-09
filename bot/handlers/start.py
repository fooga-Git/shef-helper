from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать меню 1", callback_data="show_menu")],
    ])
    await message.answer("Привет! Жми кнопку.", reply_markup=kb)


@router.callback_query(lambda c: c.data == "show_menu")
async def show_menu(callback: CallbackQuery) -> None:
    await callback.answer("Кнопка работает!")
    await callback.message.answer("Это тестовое меню.")
