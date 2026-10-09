from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu(role: str) -> ReplyKeyboardMarkup:
    buttons = []
    if role == "chef":
        buttons.append([KeyboardButton(text="👔 Администрация команды")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
